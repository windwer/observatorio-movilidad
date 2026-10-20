"""Local/private GTFS Observatory API. Launch using `python app.py`."""
import os
import hmac
import secrets
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
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('OBS_DB',ROOT/'data'/'observatorio.sqlite3'))
HOST=os.environ.get('OBS_HOST','127.0.0.1')
PASSWORD=os.environ.get('OBS_PASSWORD')
USERNAME=os.environ.get('OBS_USERNAME','analista')
APP_VERSION='0.6.6'
if HOST not in ('127.0.0.1','localhost','::1'):
    if not PASSWORD or len(PASSWORD)<24 or PASSWORD.startswith(('CHANGE_ME','password','Password')):
        raise RuntimeError('Acceso remoto no permitido sin una OBS_PASSWORD fuerte (mínimo 24 caracteres). Requiere también HTTPS en el proxy.')
app=FastAPI(title='Observatorio Bidasoaldea y Oarsoaldea', version=APP_VERSION,docs_url=None,redoc_url=None,openapi_url=None)
@app.middleware('http')
async def demo_readonly(request:Request,call_next):
    if os.environ.get('OBS_DEMO')=='1' and request.method!='GET' and (request.url.path.startswith('/api/') or request.url.path.startswith('/internal/')):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Modo product review: las operaciones de escritura y las descargas externas están bloqueadas hasta la aprobación del Product Manager.'},status_code=403)
    return await call_next(request)

_TERRITORY=None
def geo_store():
    global _TERRITORY
    destination=DB.parent/'geography'
    if _TERRITORY is None or _TERRITORY.directory!=destination:
        _TERRITORY=territory.TerritoryStore(destination)
    return _TERRITORY
security=HTTPBasic(auto_error=False)

def guard(creds:HTTPBasicCredentials|None=Depends(security)):
    if PASSWORD:
        if not creds or not (secrets.compare_digest(creds.username,USERNAME) and secrets.compare_digest(creds.password,PASSWORD)):
            raise HTTPException(status_code=401,detail='Acceso privado',headers={'WWW-Authenticate':'Basic realm="Observatorio privado"'})
    return True

def db(): return engine.connect(DB)

def handle(func,*args,**kwargs):
    con=db()
    try: return func(con,*args,**kwargs)
    except ValueError as e: raise HTTPException(status_code=400,detail=str(e))
    finally: con.close()

@app.get('/')
def home(_:bool=Depends(guard)):
    return FileResponse(ROOT/'static'/'index.html', headers={'Cache-Control':'no-store'})


# Official census table: tabular reference only; isochrone population requires
# matching GeoEuskadi polygons and residential buildings separately.
def ensure_population():
    return population_reference.load_if_needed(DB, ROOT/'data'/'references'/'eustat_2025_original.csv')

@app.get('/api/population/status')
def population_status(_:bool=Depends(guard)):
    return ensure_population()

@app.get('/api/population/sections')
def population_sections(municipality:str='',_:bool=Depends(guard)):
    ensure_population()
    try:return population_reference.sections(DB,municipality)
    except ValueError as e:raise HTTPException(status_code=400,detail=str(e))

@app.post('/api/population/import')
async def population_import(file:UploadFile=File(...),_:bool=Depends(guard)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400,detail='Solo se acepta un CSV oficial Eustat')
    raw=await file.read(2_000_001)
    if len(raw)>2_000_000:
        raise HTTPException(status_code=413,detail='CSV demasiado grande')
    try:
        result=population_reference.ingest(DB,raw,source_name=file.filename)
        dest=ROOT/'data'/'references'/'eustat_2025_original.csv'
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
        return result
    except ValueError as ex:
        raise HTTPException(status_code=422,detail=str(ex))

@app.get('/api/health')
def health(_:bool=Depends(guard)):
    return {'ok':True,'cutoff':engine.CUTOFF.isoformat(),'scope':'Ekialdebus + Irunbus / seis municipios','published':False,'observed_service':False,'version':APP_VERSION,'historical_service_certified':False}

@app.get('/api/versions')
def versions(_:bool=Depends(guard)):
    return handle(engine.versions)

@app.post('/api/import')
async def upload(operator:str=Form(...),snapshot_date:str=Form(...),file:UploadFile=File(...),_:bool=Depends(guard)):
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400,detail='Se requiere un GTFS .zip')
    # Limit before reading unbounded content
    content=await file.read(90_000_001)
    return handle(engine.ingest,content,operator,snapshot_date,file.filename)

@app.get('/api/month')
def month(operator:str='ekialdebus',year:int=2026,month:int=10,day_type:str='LJ',hour_start:int=0,hour_end:int=2880,route_id:str='',calendar_filter:str='all',_:bool=Depends(guard)):
    if not (0<=hour_start<hour_end<=2880):
        raise HTTPException(status_code=400,detail='Intervalo horario inválido')
    return handle(engine.month_analysis,operator,year,month,day_type,hour_start,hour_end,route_id,calendar_filter)

@app.get('/api/routes')
def routes(operator:str='ekialdebus',year:int=2026,month:int=10,_:bool=Depends(guard)):
    """Return the stable line catalogue independently from the day filter."""
    return handle(engine.route_catalog,operator,year,month)

@app.get('/api/compare')
def compare(operator:str='ekialdebus',month:int=10,day_type:str='LJ',hour_start:int=0,hour_end:int=2880,_:bool=Depends(guard)):
    if hour_start<0 or hour_end>2880 or hour_start>=hour_end:
        raise HTTPException(status_code=400,detail='Intervalo horario inválido')
    return handle(engine.historical_comparison,operator,month,day_type,hour_start,hour_end)

@app.get('/api/map')
def map_view(operator:str='ekialdebus',day:str='2026-10-16',route_id:str='',_:bool=Depends(guard)):
    return handle(engine.map_data,operator,day,route_id)

@app.get('/api/route/metrics')
def route_metrics(operator:str,route_id:str,day:str,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id:
        raise HTTPException(status_code=400,detail='Línea u operador inválido')
    return handle(route_insights.route_metrics,operator,route_id,day)

@app.get('/api/route/frequency')
def route_frequency(operator:str,route_id:str,year:int=2026,month:int=10,day:str='2026-10-16',_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id or year not in (2025,2026) or month not in range(1,13):
        raise HTTPException(status_code=400,detail='Selección inválida')
    return handle(route_insights.route_frequency_week,operator,route_id,year,month,day)

@app.get('/api/route/compare')
def route_compare(operator:str,route_id:str,old_day:str='2025-10-16',new_day:str='2026-10-16',_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or not route_id:
        raise HTTPException(status_code=400,detail='Línea u operador inválido')
    return handle(route_insights.route_comparison,operator,route_id,old_day,new_day)

@app.get('/api/map/both')
def map_both(day:str='2026-10-16',_:bool=Depends(guard)):
    day=engine.clean_date(day)
    con=db()
    try:
        responses={op:engine.map_data(con,op,day) for op in engine.OPERATORS}
        missing=[op for op,r in responses.items() if r['quality']=='missing']
        routes=[];stops=[]
        for op,r in responses.items():
            routes.extend([{**route,'id':op+':'+route['id'],'operator':op} for route in r['routes']])
            stops.extend([{**stop,'operator':op} for stop in r['stops']])
        return {'day':day,'state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
            'quality':'missing' if len(missing)==len(engine.OPERATORS) else 'partial' if missing else 'available_unverified',
            'missing_operators':missing,'routes':routes,'stops':stops,
            'sources':{op:{'feed_id':r.get('feed_id'),'quality':r['quality']} for op,r in responses.items()},
            'certified':False,'note':'Superposición geográfica; paradas próximas entre operadores pueden coincidir. Fuente faltante no implica ausencia de servicio.'}
    finally:con.close()

@app.get('/api/stop')
def stop(operator:str,day:str,stop_id:str,_:bool=Depends(guard)):
    return handle(engine.stop_departures,operator,day,stop_id)

@app.get('/api/coverage')
def coverage(operator:str='ekialdebus',year:int=2026,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS or year not in (2025,2026):
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
async def geo_import(layer:str=Form(...),file:UploadFile=File(...),_:bool=Depends(guard)):
    if not file.filename.lower().endswith(('.geojson','.json')):
        raise HTTPException(status_code=400,detail='Se necesita GeoJSON (FeatureCollection)')
    raw=await file.read(55_000_001)
    try:return geo_store().ingest(layer,raw)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(status_code=400,detail=str(e))

@app.get('/api/geo/network')
def geo_network(operator:str,day:str,route_id:str='',minutes:int=10,_:bool=Depends(guard)):
    if operator not in engine.OPERATORS and operator!='both':raise HTTPException(status_code=400,detail='Operador inválido')
    if minutes not in (5,10):raise HTTPException(status_code=400,detail='Se admiten coberturas de 5 y 10 minutos')
    con=db()
    try:
        ops=tuple(engine.OPERATORS) if operator=='both' else (operator,)
        records=[engine.map_data(con,op,day) for op in ops]
        missing=[op for op,r in zip(ops,records) if r['quality']=='missing']
        if missing:
            return {'status':'missing_gtfs','population':None,'missing_operators':missing,
                    'operator':operator,'day':day,'certified':False}
        stops=[{**s,'operator':op} for op,r in zip(ops,records) for s in engine.map_data(con,op,day,route_id)['stops']]
        return {'operator':operator,'day':day,'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
                'route_id':route_id or None,'minutes':minutes,
                'source_quality':{op:r['quality'] for op,r in zip(ops,records)},
                **geo_store().network_coverage(stops,minutes=minutes)}
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
def refresh_gtfs(operator:str, _:bool=Depends(guard)):
    """Explicitly requested download of the latest current GTFS, not historical certification."""
    if operator not in engine.OPERATORS:raise HTTPException(status_code=400,detail='Operador inválido')
    try:
        content=source_fetch.fetch_gtfs(operator)
        return handle(engine.ingest,content,operator,__import__('datetime').date.today().isoformat(),f'{operator}_current_from_NAP_mirror.zip')
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo descargar el feed oficial: '+str(e)[:300])

@app.post('/api/sources/osm')
def refresh_osm(_:bool=Depends(guard)):
    try:
        raw=source_fetch.fetch_osm_walkways()
        return geo_store().ingest('walkways',raw)
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo obtener la red OSM: '+str(e)[:250])

@app.post('/api/sources/buildings')
def refresh_buildings(_:bool=Depends(guard)):
    try:
        raw=source_fetch.fetch_osm_buildings()
        return geo_store().ingest('buildings',raw)
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudieron obtener edificios residenciales: '+str(e)[:250])

@app.post('/api/sources/reference')
def refresh_reference(name:str,_:bool=Depends(guard)):
    if name not in ('eustat_csv','census_geometry'):
        raise HTTPException(status_code=400,detail='Fuente no autorizada')
    try:
        ext='.csv' if name=='eustat_csv' else '.zip'
        return source_fetch.fetch_reference(name,DB.parent/'references'/(name+ext))
    except (OSError,TimeoutError,ValueError) as e:
        raise HTTPException(status_code=502,detail='No se pudo obtener referencia: '+str(e)[:250])

@app.get('/api/data/requirements')
def data_requirements(_:bool=Depends(guard)):
    return {'cutoff':engine.CUTOFF.isoformat(),'operators':list(engine.OPERATORS),
       'municipalities':list(territory.MUNICIPALITIES),
       'geography_required':{'census':'GeoJSON Polygon with section_id, municipality, population; Eustat 2025',
        'buildings':'GeoJSON Polygon with building=residential/house/apartments etc; floor count optional',
        'walkways':'GeoJSON LineString with highway, foot and access tags; from OpenStreetMap'},
       'verified_historical_dates':False,
       'source_urls':{'ekialdebus':'https://gtfs-source-feeds.transit.land/es-nap-1201.zip',
                      'irunbus':'https://gtfs-source-feeds.transit.land/es-nap-1199.zip',
                      'population':'https://es.eustat.eus/elementos/xls0011434_c.csv'},
       'no_data_means_zero':False}

class HistoricalReview(BaseModel):
    operator:str
    from_date:str
    to_date:str
    reviewer:str=Field(min_length=3,max_length=160)
    evidence:str=Field(min_length=15,max_length=3000)
    status:str='verified'

@app.get('/api/audit/readiness')
def audit_readiness(_:bool=Depends(guard)):
    con=db()
    try:return audit.readiness(con,geo_store().status())
    finally:con.close()

@app.get('/api/audit/month-grid')
def audit_month_grid(operator:str='ekialdebus',year:int=2026,_:bool=Depends(guard)):
    return handle(audit.month_grid,operator,year)

@app.post('/api/audit/review')
def audit_review(body:HistoricalReview,_:bool=Depends(guard)):
    return handle(audit.review_period,body.operator,body.from_date,body.to_date,
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
    op_list=tuple(engine.OPERATORS) if operator=='both' else (operator,)
    con=db()
    try:
        sources=[offer.stop_service_offer(con,op,day,hour_start,hour_end) for op in op_list]
        if any(x['status']=='missing_gtfs' for x in sources):
            return {'status':'missing_gtfs','population_by_frequency':None,
                    'missing_operators':[x['operator'] for x in sources if x['status']=='missing_gtfs'],
                    'certified':False,'day':day,'operator':operator}
        store=geo_store()
        if not store.status()['ready']:
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
            raise HTTPException(status_code=422,detail='Para limitar a los seis municipios, carga primero la cartografía censal. Puedes desactivar territorial_scope para comparar toda la red.')
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
    return {'version':APP_VERSION,'date_cutoff':'2026-10-18','data_state':'unverified_until_audit','api_schema':'v0.6.6','package':'historical-real-gtfs'}

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
    response.headers['Cache-Control']='private, no-store'
    return response

app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')

@app.get('/api/demo/status')
def demo_status(_:bool=Depends(guard)):
    demo=os.environ.get('OBS_DEMO','0')=='1'
    note=('Oferta, recorridos y paradas son DEMO; la red peatonal incluida es OSM real y la accesibilidad sigue pendiente de Product Review.'
          if demo else
          'GTFS reales importados desde las dos instantáneas entregadas por el usuario. La oferta es programada, no prueba servicio prestado; la población cubierta requiere capas censales y residenciales verificables.')
    return {'demo':demo,'version':APP_VERSION,'note':note}

@app.get('/api/demo/catalog')
def demo_catalog(operator:str='ekialdebus',year:int=2026,month:int=10,_:bool=Depends(guard)):
    """All known DEMO lines for period, including ones not operated on selected weekday."""
    if os.environ.get('OBS_DEMO')!='1':raise HTTPException(status_code=404,detail='Solo disponible en product review')
    if operator not in engine.OPERATORS or year not in (2025,2026) or month not in range(1,13):
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
    print(f"Observatorio {APP_VERSION} privado local: http://{HOST}:{os.environ.get('OBS_PORT','8765')}")
    uvicorn.run(app,host=HOST,port=int(os.environ.get('OBS_PORT','8765')))

