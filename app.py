"""Local/private GTFS Observatory API. Launch using `python app.py`."""
import os
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque, OrderedDict
from datetime import date
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends
import uvicorn
import engine
import route_insights
import territory
import source_fetch
import audit
import changes
import offer
import network_compare
import data_quality
import population_reference
import settings
import analysis_jobs
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parent
CONFIG=settings.SETTINGS
DB=CONFIG.db
HOST=CONFIG.host
# Legacy aliases remain mutable for older local integrations and tests. Reads
# and administration are nevertheless checked by different dependencies.
PASSWORD=CONFIG.reader_password
USERNAME=CONFIG.reader_username
ADMIN_PASSWORD=CONFIG.admin_password
ADMIN_USERNAME=CONFIG.admin_username
APP_VERSION=settings.APP_VERSION
app=FastAPI(title='Observatorio de Movilidad · Gipuzkoa', version=APP_VERSION,docs_url=None,redoc_url=None,openapi_url=None)
_REQUESTS=defaultdict(int);_LATENCY_MS=defaultdict(float);_RATE=defaultdict(deque);_METRICS_LOCK=threading.Lock()
_READ_CACHE=OrderedDict();_READ_CACHE_LOCK=threading.RLock();_READ_KEY_LOCKS=defaultdict(threading.Lock)

def cached_read(key,loader,max_entries=128):
    """Bounded request cache with per-key single-flight on cold reads."""
    try:stamp=Path(DB).stat().st_mtime_ns
    except OSError:stamp=0
    full=(str(Path(DB).resolve()),stamp,*key)
    with _READ_CACHE_LOCK:
        if full in _READ_CACHE:
            value=_READ_CACHE[full];_READ_CACHE.move_to_end(full);return value
        lock=_READ_KEY_LOCKS[full]
    with lock:
        with _READ_CACHE_LOCK:
            if full in _READ_CACHE:
                value=_READ_CACHE[full];_READ_CACHE.move_to_end(full);return value
        value=loader()
        with _READ_CACHE_LOCK:
            _READ_CACHE[full]=value;_READ_CACHE.move_to_end(full)
            while len(_READ_CACHE)>max_entries:_READ_CACHE.popitem(last=False)
            _READ_KEY_LOCKS.pop(full,None)
        return value

@app.middleware('http')
async def request_budget_and_metrics(request:Request,call_next):
    started=time.perf_counter();path=request.url.path
    client=(request.client.host if request.client else 'unknown')
    if path.startswith('/api/') and path not in ('/api/health','/api/ready'):
        now=time.monotonic()
        with _METRICS_LOCK:
            bucket=_RATE[client]
            while bucket and bucket[0] < now-60:bucket.popleft()
            if len(bucket)>=CONFIG.rate_limit_per_minute:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Demasiadas solicitudes; inténtalo de nuevo en un minuto'},status_code=429,
                                    headers={'Retry-After':'60'})
            bucket.append(now)
    response=await call_next(request)
    elapsed=(time.perf_counter()-started)*1000
    key=f'{request.method} {path} {response.status_code}'
    with _METRICS_LOCK:
        _REQUESTS[key]+=1;_LATENCY_MS[key]+=elapsed
    response.headers['X-Response-Time-Ms']=f'{elapsed:.1f}'
    return response
@app.middleware('http')
async def demo_readonly(request:Request,call_next):
    if os.environ.get('OBS_DEMO')=='1' and request.method!='GET' and (request.url.path.startswith('/api/') or request.url.path.startswith('/internal/')):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Modo product review: las operaciones de escritura y las descargas externas están bloqueadas hasta la aprobación del Product Manager.'},status_code=403)
    return await call_next(request)

_TERRITORY=None
_TERRITORY_LOCK=threading.Lock()
def geo_store():
    global _TERRITORY
    destination=CONFIG.geography_dir if Path(DB).resolve()==CONFIG.db else DB.parent/'geography'
    # A real-data package may be copied without its runtime folder having
    # been created yet.  Reuse the packaged, verified geography only for the
    # named real database; temporary/test databases must remain isolated and
    # must not inherit production population figures.
    if DB.name.lower()=='observatorio_real.sqlite3':
        bundled=ROOT/'data'/'real'/'geography'
        required=('census.geojson','walkways.geojson')
        if not all((destination/name).is_file() for name in required) and all((bundled/name).is_file() for name in required):
            destination=bundled
    if _TERRITORY is None or _TERRITORY.directory!=destination:
        with _TERRITORY_LOCK:
            if _TERRITORY is None or _TERRITORY.directory!=destination:
                _TERRITORY=territory.TerritoryStore(destination,cache_entries=CONFIG.cache_entries)
    return _TERRITORY
security=HTTPBasic(auto_error=False)

def guard(creds:HTTPBasicCredentials|None=Depends(security)):
    # An explicitly configured legacy password keeps private-reader behaviour.
    if PASSWORD or not CONFIG.public_read:
        if not PASSWORD:
            raise HTTPException(status_code=503,detail='Lectura privada sin credencial configurada')
        if not creds or not (secrets.compare_digest(creds.username,USERNAME) and secrets.compare_digest(creds.password,PASSWORD)):
            raise HTTPException(status_code=401,detail='Acceso de lectura privado',headers={'WWW-Authenticate':'Basic realm="Observatorio lectura"'})
    return True

def admin_guard(creds:HTTPBasicCredentials|None=Depends(security)):
    password=ADMIN_PASSWORD or PASSWORD
    username=ADMIN_USERNAME if ADMIN_PASSWORD else USERNAME
    if password:
        if not creds or not (secrets.compare_digest(creds.username,username) and secrets.compare_digest(creds.password,password)):
            raise HTTPException(status_code=401,detail='Administración restringida',headers={'WWW-Authenticate':'Basic realm="Observatorio administracion"'})
    elif not CONFIG.writable_local_admin:
        raise HTTPException(status_code=403,detail='Administración deshabilitada: configura OBS_ADMIN_PASSWORD')
    return True

def write_guard(_:bool=Depends(admin_guard)):
    if CONFIG.immutable_data:
        raise HTTPException(status_code=403,detail='Esta release es inmutable; las importaciones se preparan fuera del servicio')
    return True

def db(): return engine.connect(DB,readonly=True,initialize=False)
def write_db(): return engine.connect(DB,readonly=False,initialize=True)

def prepare_runtime():
    """Apply migrations once before accepting traffic and initialise state."""
    if CONFIG.immutable_data:
        con=engine.connect(DB,readonly=True,initialize=False)
        try:con.execute('SELECT 1 FROM schema_migrations LIMIT 1')
        finally:con.close()
        return
    con=engine.connect(DB,readonly=False,initialize=True)
    con.close()

def handle(func,*args,**kwargs):
    con=db()
    try: return func(con,*args,**kwargs)
    except ValueError as e: raise HTTPException(status_code=400,detail=str(e))
    finally: con.close()

def handle_write(func,*args,**kwargs):
    con=write_db()
    try:return func(con,*args,**kwargs)
    except ValueError as e:raise HTTPException(status_code=400,detail=str(e))
    finally:con.close()

@app.get('/')
def home(_:bool=Depends(guard)):
    return FileResponse(ROOT/'static'/'index.html', headers={'Cache-Control':'no-store'})


# Official census table: tabular reference plus the separately packaged INE
# section geometries and OSM pedestrian graph used for isochrone estimates.
def ensure_population():
    return population_reference.summary(DB)

@app.get('/api/population/status')
def population_status(_:bool=Depends(guard)):
    population=ensure_population()
    # The CSV import intentionally remains a tabular source of truth.  The
    # runtime endpoint additionally reports whether this instance has the
    # separately packaged census polygons and pedestrian graph needed for an
    # area-interpolated target-population estimate.
    if not population.get('loaded'):
        return population
    try:
        geo=geo_store().status()
        geography_population=geo.get('census_population',0) or 0
        geography_complete=bool(geo.get('population_access_ready') and geography_population==population.get('total_population'))
        population={**population,
            'geometry_joined':bool(geo.get('census_sections')),
            'geography_complete':geography_complete,
            'geography_scope':'Gipuzkoa' if geography_complete else 'Gipuzkoa (geometría provincial pendiente)',
            'spatial_coverage_ready':bool(geo.get('population_access_ready')),
            'area_interpolation_ready':False,
            'geography':{'census_sections':geo.get('census_sections',0),
                         'walk_segments':geo.get('walk_segments',0),
                         'residential_buildings':geo.get('residential_buildings',0),
                         'census_population':geography_population,
                         'population_method':geo.get('population_method','unavailable'),
                         'method_version':geo.get('method_version')}}
        if population['spatial_coverage_ready']:
            population['note']=('Población Eustat 2025 cruzada con secciones censales y red peatonal; '
                'la cobertura es una estimación por unidades asignadas a la red peatonal, no demanda observada. '
                + ('La geometría cubre Gipuzkoa.' if geography_complete else
                   'La geometría disponible cubre por ahora sólo Bidasoaldea y Oarsoaldea.'))
    except (OSError,ValueError,TypeError):
        # Keep the validated tabular population available even if the optional
        # geography package is absent or malformed.
        pass
    return population

@app.get('/api/population/sections')
def population_sections(municipality:str='',_:bool=Depends(guard)):
    ensure_population()
    try:return population_reference.sections(DB,municipality)
    except ValueError as e:raise HTTPException(status_code=400,detail=str(e))

@app.post('/api/population/import')
async def population_import(file:UploadFile=File(...),_:bool=Depends(write_guard)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400,detail='Solo se acepta un CSV oficial Eustat')
    raw=await file.read(2_000_001)
    if len(raw)>2_000_000:
        raise HTTPException(status_code=413,detail='CSV demasiado grande')
    try:
        result=population_reference.ingest(DB,raw,source_name=file.filename)
        dest=CONFIG.reference_csv
        dest.parent.mkdir(parents=True,exist_ok=True)
        pending=dest.with_suffix(dest.suffix+'.pending')
        pending.write_bytes(raw);pending.replace(dest)
        return result
    except ValueError as ex:
        raise HTTPException(status_code=422,detail=str(ex))

@app.get('/api/health')
def health(_:bool=Depends(guard)):
    return {'ok':True,'kind':'liveness','cutoff':engine.CUTOFF.isoformat(),'scope':'Gipuzkoa: población Eustat 2025; transporte y cobertura peatonal según fuentes cargadas','published':False,'observed_service':False,'version':APP_VERSION,'historical_service_certified':False}

@app.get('/api/ready')
def ready(_:bool=Depends(guard)):
    checks={'database':False,'feeds':0,'census_file':False,'walkways_file':False,'population_reference':False}
    try:
        con=db()
        try:
            checks['feeds']=int(con.execute('SELECT COUNT(*) FROM feeds').fetchone()[0])
            checks['database']=True
            checks['population_reference']=bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='population_reference_meta'").fetchone())
        finally:con.close()
    except (OSError,FileNotFoundError,ValueError):pass
    checks['census_file']=(CONFIG.geography_dir/'census.geojson').is_file()
    checks['walkways_file']=(CONFIG.geography_dir/'walkways.geojson').is_file()
    ok=checks['database'] and checks['feeds']>0 and checks['census_file'] and checks['walkways_file'] and checks['population_reference']
    if not ok:raise HTTPException(status_code=503,detail={'ready':False,'checks':checks})
    return {'ready':True,'kind':'readiness','checks':checks,'data_release':os.environ.get('OBS_DATA_RELEASE','local-unversioned'),
            'method_version':settings.METHOD_VERSION}

@app.get('/api/metrics')
def metrics(_:bool=Depends(admin_guard)):
    with _METRICS_LOCK:
        rows=[{'request':key,'count':count,'average_ms':round(_LATENCY_MS[key]/count,1)}
              for key,count in sorted(_REQUESTS.items()) if count]
    return {'requests':rows,'iso_cache':geo_store().cache_status() if _TERRITORY is not None else {'loaded':False}}

@app.get('/api/versions')
def versions(_:bool=Depends(guard)):
    return handle(engine.versions)

@app.post('/api/import')
async def upload(operator:str=Form(...),snapshot_date:str=Form(...),file:UploadFile=File(...),_:bool=Depends(write_guard)):
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400,detail='Se requiere un GTFS .zip')
    # Limit before reading unbounded content
    content=await file.read(90_000_001)
    return handle_write(engine.ingest,content,operator,snapshot_date,file.filename)

@app.get('/api/month')
def month(operator:str='ekialdebus',year:int=2026,month:int=10,day_type:str='LJ',hour_start:int=0,hour_end:int=2880,route_id:str='',calendar_filter:str='all',_:bool=Depends(guard)):
    if not (0<=hour_start<hour_end<=2880):
        raise HTTPException(status_code=400,detail='Intervalo horario inválido')
    return cached_read(('month',operator,year,month,day_type,hour_start,hour_end,route_id,calendar_filter),
        lambda:handle(engine.month_analysis,operator,year,month,day_type,hour_start,hour_end,route_id,calendar_filter))

@app.get('/api/routes')
def routes(operator:str='ekialdebus',year:int=2026,month:int=10,_:bool=Depends(guard)):
    """Return the stable line catalogue independently from the day filter."""
    return cached_read(('routes',operator,year,month),lambda:handle(engine.route_catalog,operator,year,month))

@app.get('/api/compare')
def compare(operator:str='ekialdebus',month:int=10,day_type:str='LJ',hour_start:int=0,hour_end:int=2880,_:bool=Depends(guard)):
    if hour_start<0 or hour_end>2880 or hour_start>=hour_end:
        raise HTTPException(status_code=400,detail='Intervalo horario inválido')
    return cached_read(('compare',operator,month,day_type,hour_start,hour_end),
        lambda:handle(engine.historical_comparison,operator,month,day_type,hour_start,hour_end))

@app.get('/api/map')
def map_view(operator:str='ekialdebus',day:str='2026-10-16',route_id:str='',_:bool=Depends(guard)):
    return cached_read(('map',operator,day,route_id),lambda:handle(engine.map_data,operator,day,route_id))

@app.get('/api/route/metrics')
def route_metrics(operator:str,route_id:str,day:str,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id:
        raise HTTPException(status_code=400,detail='Línea u operador inválido')
    return handle(route_insights.route_metrics,operator,route_id,day)

@app.get('/api/route/frequency')
def route_frequency(operator:str,route_id:str,year:int=2026,month:int=10,day:str='2026-10-16',_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id or not CONFIG.min_year<=year<=CONFIG.max_year or month not in range(1,13):
        raise HTTPException(status_code=400,detail='Selección inválida')
    return handle(route_insights.route_frequency_week,operator,route_id,year,month,day)

@app.get('/api/route/compare')
def route_compare(operator:str,route_id:str,old_day:str='2025-10-16',new_day:str='2026-10-16',_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id:
        raise HTTPException(status_code=400,detail='Línea u operador inválido')
    return handle(route_insights.route_comparison,operator,route_id,old_day,new_day)

@app.get('/api/map/both')
def map_both(day:str='2026-10-16',scope:str='core',_:bool=Depends(guard)):
    if scope not in ('core','all'):
        raise HTTPException(status_code=400,detail='Alcance de mapa inválido')
    day=engine.clean_date(day)
    con=db()
    try:
        # Keep the default endpoint compatible with the historical two-bus
        # comparison.  The map can explicitly request every loaded operator.
        operators=engine.CORE_OPERATORS if scope=='core' else tuple(engine.OPERATORS)
        responses={op:engine.map_data(con,op,day) for op in operators}
        missing=[op for op,r in responses.items() if r['quality']=='missing']
        routes=[];stops=[]
        for op,r in responses.items():
            routes.extend([{**route,'id':op+':'+route['id'],'operator':op} for route in r['routes']])
            stops.extend([{**stop,'operator':op} for stop in r['stops']])
        return {'day':day,'state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
            'quality':'missing' if len(missing)==len(operators) else 'partial' if missing else 'available_unverified',
            'missing_operators':missing,'routes':routes,'stops':stops,
            'sources':{op:{'feed_id':r.get('feed_id'),'quality':r['quality']} for op,r in responses.items()},
            'scope':scope,'operators':list(operators),'certified':False,
            'note':'Superposición geográfica; paradas próximas entre operadores pueden coincidir. Fuente faltante no implica ausencia de servicio.'}
    finally:con.close()

@app.get('/api/stop')
def stop(operator:str,day:str,stop_id:str,_:bool=Depends(guard)):
    return handle(engine.stop_departures,operator,day,stop_id)

@app.get('/api/coverage')
def coverage(operator:str='ekialdebus',year:int=2026,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not CONFIG.min_year<=year<=CONFIG.max_year:
        raise HTTPException(status_code=400,detail='Filtros inválidos')
    con=db()
    try:
        from calendar import monthrange
        matrix=[]
        for m in range(1,13):
            first=date(year,m,1);last=date(year,m,monthrange(year,m)[1])
            found=0;retro=0
            cursor=first
            from datetime import timedelta
            while cursor<=last:
                v,q=engine.pick_version(con,operator,cursor.isoformat())
                if v: found+=1
                if q=='retrospective_snapshot': retro+=1
                cursor+=timedelta(days=1)
            matrix.append({'month':m,'days':last.day,'with_source':found,'without_source':last.day-found,'retrospective':retro,
                'state':'historical' if last<=engine.CUTOFF else 'planning' if first>engine.CUTOFF else 'mixed'})
        return {'operator':operator,'year':year,'cutoff':engine.CUTOFF.isoformat(),'months':matrix,
                'note':'Con fuente no implica validado ni servicio realmente prestado'}
    finally:con.close()

@app.get('/api/geo/status')
def geo_status(_:bool=Depends(guard)):
    return geo_store().status()

@app.post('/api/geo/import')
async def geo_import(layer:str=Form(...),file:UploadFile=File(...),_:bool=Depends(write_guard)):
    if not file.filename.lower().endswith(('.geojson','.json')):
        raise HTTPException(status_code=400,detail='Se necesita GeoJSON (FeatureCollection)')
    raw=await file.read(180_000_001)
    try:return geo_store().ingest(layer,raw)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(status_code=400,detail=str(e))

@app.get('/api/geo/network')
def geo_network(operator:str,day:str,route_id:str='',minutes:int=10,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS and operator not in ('both','all'):raise HTTPException(status_code=400,detail='Operador inválido')
    if minutes not in (5,10):raise HTTPException(status_code=400,detail='Se admiten coberturas de 5 y 10 minutos')
    con=db()
    try:
        ops=engine.CORE_OPERATORS if operator=='both' else tuple(engine.OPERATORS) if operator=='all' else (operator,)
        records=[engine.map_data(con,op,day) for op in ops]
        missing=[op for op,r in zip(ops,records) if r['quality']=='missing']
        if missing and operator!='all':
            return {'status':'missing_gtfs','population':None,'missing_operators':missing,
                    'operator':operator,'day':day,'certified':False}
        available=[(op,r) for op,r in zip(ops,records) if r['quality']!='missing']
        if not available:
            return {'status':'missing_gtfs','population':None,'missing_operators':missing,
                    'operator':operator,'day':day,'certified':False}
        stops=[{**s,'operator':op} for op,_ in available for s in engine.map_data(con,op,day,route_id)['stops']]
        result={'operator':operator,'day':day,'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
                'route_id':route_id or None,'minutes':minutes,
                'source_quality':{op:r['quality'] for op,r in available},
                'missing_operators':missing,
                **geo_store().network_coverage(stops,minutes=minutes)}
        if missing:result['status']='partial_sources'
        return result
    except ValueError as e:raise HTTPException(status_code=400,detail=str(e))
    finally:con.close()

@app.get('/api/geo/stop')
def geo_stop(operator:str,day:str,stop_id:str,minutes:int=10,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS:raise HTTPException(status_code=400,detail='Operador inválido')
    if minutes not in (5,10):raise HTTPException(status_code=400,detail='Se admiten isócronas de 5 y 10 minutos')
    try:day=engine.clean_date(day)
    except ValueError:raise HTTPException(status_code=400,detail='Fecha inválida')
    con=db()
    try:
        version,quality=engine.pick_version(con,operator,day)
        if version is None:raise HTTPException(status_code=404,detail='Sin GTFS para la fecha indicada')
        s=con.execute('SELECT lat,lon,name FROM stops WHERE feed_id=? AND stop_id=?',(version['id'],stop_id)).fetchone()
        if not s:raise HTTPException(status_code=404,detail='Parada no encontrada')
        if s['lat'] is None or s['lon'] is None:raise HTTPException(status_code=422,detail='La parada carece de coordenadas')
        return {'operator':operator,'day':day,'stop_id':stop_id,'stop_name':s['name'],
          'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
          'source_quality':quality,**geo_store().stop(s['lat'],s['lon'],minutes=minutes)}
    finally:con.close()

@app.post('/api/sources/refresh')
def refresh_gtfs(operator:str, _:bool=Depends(write_guard)):
    """Explicitly requested download of the latest current GTFS, not historical certification."""
    if operator not in engine.OPERATORS:raise HTTPException(status_code=400,detail='Operador inválido')
    try:
        content=source_fetch.fetch_gtfs(operator)
        return handle_write(engine.ingest,content,operator,__import__('datetime').date.today().isoformat(),f'{operator}_current_from_Moveuskadi.zip')
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo descargar el feed oficial: '+str(e)[:300])

@app.post('/api/sources/osm')
def refresh_osm(_:bool=Depends(write_guard)):
    try:
        raw=source_fetch.fetch_osm_walkways()
        return geo_store().ingest('walkways',raw)
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo obtener la red OSM: '+str(e)[:250])

@app.post('/api/sources/buildings')
def refresh_buildings(_:bool=Depends(write_guard)):
    try:
        raw=source_fetch.fetch_osm_buildings()
        return geo_store().ingest('buildings',raw)
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudieron obtener edificios residenciales: '+str(e)[:250])

@app.post('/api/sources/reference')
def refresh_reference(name:str,_:bool=Depends(write_guard)):
    if name not in ('eustat_csv','census_geometry'):
        raise HTTPException(status_code=400,detail='Fuente no autorizada')
    try:
        ext='.csv' if name=='eustat_csv' else '.zip'
        return source_fetch.fetch_reference(name,DB.parent/'references'/(name+ext))
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo obtener referencia: '+str(e)[:250])

@app.get('/api/data/requirements')
def data_requirements(_:bool=Depends(guard)):
    years=[]
    try:
        con=db()
        try:
            row=con.execute("SELECT MIN(CAST(substr(min_date,1,4) AS INT)),MAX(CAST(substr(max_date,1,4) AS INT)) FROM feeds").fetchone()
            if row and row[0] and row[1]:years=list(range(max(CONFIG.min_year,int(row[0])),min(CONFIG.max_year,int(row[1]))+1))
        finally:con.close()
    except (OSError,FileNotFoundError):pass
    if not years:years=[engine.CUTOFF.year-1,engine.CUTOFF.year]
    return {'cutoff':engine.CUTOFF.isoformat(),'operators':list(engine.OPERATORS),'operator_labels':engine.OPERATORS,
       'core_operators':list(engine.CORE_OPERATORS),
       'municipalities':list(territory.MUNICIPALITIES),
       'geography_required':{'census':'GeoJSON Polygon with section_id, municipality, population; Eustat 2025 (required for target population)',
        'buildings':'Optional GeoJSON Polygon with building=residential/house/apartments etc; enables a more precise dasymetric allocation',
        'walkways':'GeoJSON LineString with highway, foot and access tags; from OpenStreetMap'},
       'verified_historical_dates':False,
       'source_urls':{'ekialdebus':'https://gtfs-source-feeds.transit.land/es-nap-1201.zip',
                      'irunbus':'https://gtfs-source-feeds.transit.land/es-nap-1199.zip',
                      'euskotren':'https://opendata.euskadi.eus/transport/moveuskadi/euskotren/gtfs_euskotren.zip',
                      'errenteria_urbanoa':'https://opendata.euskadi.eus/transport/moveuskadi/errenteria/gtfs_errenteriako_urbanoa.zip',
                      'population':'https://es.eustat.eus/elementos/xls0011434_c.csv'},
       'analysis_years':{'min':CONFIG.min_year,'max':CONFIG.max_year},'available_years':years,
       'method_version':settings.METHOD_VERSION,'no_data_means_zero':False}

class HistoricalReview(BaseModel):
    operator:str
    from_date:str
    to_date:str
    reviewer:str=Field(min_length=3,max_length=160)
    evidence:str=Field(min_length=15,max_length=3000)
    status:str='verified'

class NetworkAnalysisRequest(BaseModel):
    operator:str
    day:str
    route_id:str=''
    minutes:int=10

@app.post('/api/analysis/jobs',status_code=202)
def create_analysis_job(body:NetworkAnalysisRequest,_:bool=Depends(guard)):
    if body.operator not in engine.OPERATORS and body.operator not in ('both','all'):
        raise HTTPException(status_code=400,detail='Operador inválido')
    if body.minutes not in (5,10):raise HTTPException(status_code=400,detail='Minutos inválidos')
    try:day=engine.clean_date(body.day)
    except ValueError:raise HTTPException(status_code=400,detail='Fecha inválida')
    params={'operator':body.operator,'day':day,'route_id':body.route_id,'minutes':body.minutes}
    try:
        return analysis_jobs.enqueue(CONFIG.state_db,'network_coverage',params,
          os.environ.get('OBS_DATA_RELEASE','local-unversioned'),settings.METHOD_VERSION,CONFIG.max_pending_jobs)
    except OverflowError as exc:raise HTTPException(status_code=429,detail=str(exc),headers={'Retry-After':'30'})

@app.get('/api/analysis/jobs/{job_id}')
def analysis_job(job_id:str,_:bool=Depends(guard)):
    result=analysis_jobs.get(CONFIG.state_db,job_id)
    if result is None:raise HTTPException(status_code=404,detail='Trabajo no encontrado')
    return result

@app.post('/api/analysis/jobs/{job_id}/cancel')
def cancel_analysis_job(job_id:str,_:bool=Depends(guard)):
    result=analysis_jobs.cancel(CONFIG.state_db,job_id)
    if result is None:raise HTTPException(status_code=404,detail='Trabajo no encontrado')
    return result

@app.get('/api/audit/readiness')
def audit_readiness(_:bool=Depends(guard)):
    con=db()
    try:return audit.readiness(con,geo_store().status())
    finally:con.close()

@app.get('/api/audit/month-grid')
def audit_month_grid(operator:str='ekialdebus',year:int=2026,_:bool=Depends(guard)):
    return handle(audit.month_grid,operator,year)

@app.post('/api/audit/review')
def audit_review(body:HistoricalReview,_:bool=Depends(write_guard)):
    return handle_write(audit.review_period,body.operator,body.from_date,body.to_date,
                  body.reviewer,body.evidence,body.status)

@app.get('/api/geo/service-coverage')
def geo_service_coverage(operator:str='both',day:str='2026-10-16',
                        hour_start:int=420,hour_end:int=540,_:bool=Depends(guard)):
    if operator!='both' and operator not in engine.OPERATORS:
        raise HTTPException(status_code=400,detail='Operador desconocido')
    if not 0<=hour_start<hour_end<=2880:
        raise HTTPException(status_code=400,detail='Franja incorrecta')
    try:day=engine.clean_date(day)
    except ValueError:raise HTTPException(status_code=400,detail='Fecha incorrecta')
    op_list=engine.CORE_OPERATORS if operator=='both' else (operator,)
    con=db()
    try:
        sources=[offer.stop_service_offer(con,op,day,hour_start,hour_end) for op in op_list]
        if any(x['status']=='missing_gtfs' for x in sources):
            return {'status':'missing_gtfs','population_by_frequency':None,
                    'missing_operators':[x['operator'] for x in sources if x['status']=='missing_gtfs'],
                    'certified':False,'day':day,'operator':operator}
        store=geo_store()
        geo_status=store.status()
        if not geo_status.get('population_access_ready'):
            return {'status':'incomplete_geography','population_by_frequency':None,'day':day,
                    'operator':operator,'certified':False}
        thresholds={}
        all_stopsets={t:[] for t in (15,30,60)}
        for src in sources:
            for t in (15,30,60):all_stopsets[t].extend(src['threshold_stops'].get(t,[]))
        for threshold,stops in all_stopsets.items():
            selected=store.stops_near_study_area(stops)
            thresholds[str(threshold)]={**store.network_coverage(selected),
                'served_stops_total':len(stops),'served_stops_in_study_area':len(selected)}
        return {'status':'estimated','operator':operator,'day':day,
          'hour_start':hour_start,'hour_end':hour_end,'time_state':sources[0]['time_state'],
          'population_by_frequency':thresholds,
          'source_versions':{s['operator']:s.get('feed_id') for s in sources},
          'method':'Mayor separación entre salidas incluyendo los límites de la franja, por línea/sentido/destino con >=2 salidas; cobertura única a 10 minutos andando',
          'certified':False,'note':'Oferta programada, no demanda ni servicio observado; sin normalizar ni verificar fechas de calendario festivo.'}
    except ValueError as e:raise HTTPException(status_code=400,detail=str(e))
    finally:con.close()

@app.get('/api/diff/stops')
def diff_stops(operator:str='ekialdebus',old_day:str='2025-10-15',
               new_day:str='2026-10-15',territorial_scope:bool=True,_:bool=Depends(guard)):
    area=None
    if territorial_scope:
        from shapely.ops import unary_union
        if not geo_store().census:
            raise HTTPException(status_code=422,detail='Para limitar el análisis a Gipuzkoa, carga primero la cartografía censal provincial. Puedes desactivar territorial_scope para comparar toda la red.')
        area=unary_union([x['geometry'] for x in geo_store().census])
    return handle(changes.compare_stops,operator,old_day,new_day,65,area)


@app.get('/api/diff/routes')
def diff_routes(operator:str='ekialdebus',old_day:str='2025-10-16',new_day:str='2026-10-15',_:bool=Depends(guard)):
    return handle(network_compare.compare_routes,operator,old_day,new_day)

@app.get('/api/quality')
def data_quality_all(_:bool=Depends(guard)):
    return handle(data_quality.validate_all)

@app.get('/api/version')
def version(_:bool=Depends(guard)):
    return {'version':APP_VERSION,'date_cutoff':engine.CUTOFF.isoformat(),'data_state':'unverified_until_audit',
            'api_schema':settings.API_SCHEMA_VERSION,'method_version':settings.METHOD_VERSION,
            'package':'historical-real-gtfs','public_read':CONFIG.public_read}

@app.middleware('http')
async def safe_response_headers(request:Request,call_next):
    # A browser on another origin cannot use authenticated state-changing endpoints.
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin','')
        if origin:
            from urllib.parse import urlparse
            try:
                parsed=urlparse(origin)
                current=request.url
                if parsed.scheme not in ('http','https') or parsed.netloc!=request.headers.get('host',''):
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=403,content={'detail':'Origen de solicitud no autorizado'})
            except (ValueError,TypeError):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403,content={'detail':'Origen inválido'})
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']=('public, max-age=31536000, immutable'
        if request.url.path.startswith('/static/') else 'private, no-store')
    return response

app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')

@app.get('/api/demo/status')
def demo_status(_:bool=Depends(guard)):
    demo=os.environ.get('OBS_DEMO','0')=='1'
    note=('Oferta, recorridos y paradas son DEMO; la red peatonal incluida es OSM real y la accesibilidad sigue pendiente de Product Review.'
          if demo else
          'GTFS reales importados desde instantáneas históricas de Irunbus/Ekialdebus y publicaciones actuales Moveuskadi de Euskotren E1/E2 y Errenteria urbano. La oferta es programada, no prueba servicio prestado; la población cubierta se estima con geometría oficial de secciones Eustat y red peatonal, y mejora con edificios residenciales.')
    return {'demo':demo,'version':APP_VERSION,'note':note}

@app.get('/api/demo/catalog')
def demo_catalog(operator:str='ekialdebus',year:int=2026,month:int=10,_:bool=Depends(guard)):
    """All known DEMO lines for period, including ones not operated on selected weekday."""
    if os.environ.get('OBS_DEMO')!='1':raise HTTPException(status_code=404,detail='Solo disponible en product review')
    if operator not in engine.OPERATORS or not CONFIG.min_year<=year<=CONFIG.max_year or month not in range(1,13):
        raise HTTPException(status_code=400,detail='Selección inválida')
    con=db()
    try:
        version,quality=engine.pick_version(con,operator,f'{year}-{month:02d}-15')
        if not version:return {'operator':operator,'routes':[],'source':'missing'}
        routes=[{'route_id':r['route_id'],'name':r['short_name'] or r['route_id'],
           'long_name':r['long_name']} for r in con.execute(
            'SELECT route_id,short_name,long_name FROM routes WHERE feed_id=? ORDER BY route_id',(version['id'],))]
        return {'operator':operator,'routes':routes,'source':'synthetic_demo'}
    finally:con.close()

if __name__=='__main__':
    prepare_runtime()
    print(f"Observatorio {APP_VERSION} local: http://{HOST}:{CONFIG.port}")
    uvicorn.run(app,host=HOST,port=CONFIG.port)

