"""Single-purpose local worker for durable geographic analysis jobs."""
from __future__ import annotations

import json
import signal
import time

import analysis_jobs
import engine
import settings
import territory


STOP=False


def _stop(*_args):
    global STOP;STOP=True


def network_coverage(store,params):
    operator=params['operator'];day=engine.clean_date(params['day']);route_id=params.get('route_id','')
    minutes=int(params.get('minutes',10))
    if operator not in engine.OPERATORS and operator not in ('both','all'):raise ValueError('Operador inválido')
    if minutes not in (5,10):raise ValueError('Minutos inválidos')
    ops=engine.CORE_OPERATORS if operator=='both' else tuple(engine.OPERATORS) if operator=='all' else (operator,)
    conn=engine.connect(settings.SETTINGS.db,readonly=True,initialize=False)
    try:
        records=[engine.map_data(conn,op,day,route_id) for op in ops]
        missing=[op for op,row in zip(ops,records) if row['quality']=='missing']
        available=[(op,row) for op,row in zip(ops,records) if row['quality']!='missing']
        if not available:return {'status':'missing_gtfs','population':None,'missing_operators':missing}
        stops=[{**stop,'operator':op} for op,record in available for stop in record['stops']]
        result={'operator':operator,'day':day,'route_id':route_id or None,'minutes':minutes,
                'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
                'source_quality':{op:row['quality'] for op,row in available},'missing_operators':missing,
                **store.network_coverage(stops,minutes)}
        if missing:result['status']='partial_sources'
        return result
    finally:conn.close()


def run_once(store):
    row=analysis_jobs.claim(settings.SETTINGS.state_db,settings.SETTINGS.job_timeout_seconds)
    if row is None:return False
    try:
        params=json.loads(row['params_json'])
        if row['kind']=='network_coverage':result=network_coverage(store,params)
        else:raise ValueError('Tipo de trabajo no permitido')
        analysis_jobs.finish(settings.SETTINGS.state_db,row['id'],result=result)
    except Exception as exc:
        analysis_jobs.finish(settings.SETTINGS.state_db,row['id'],error=f'{type(exc).__name__}: {exc}')
    return True


def main():
    signal.signal(signal.SIGINT,_stop);signal.signal(signal.SIGTERM,_stop)
    store=territory.TerritoryStore(settings.SETTINGS.geography_dir,cache_entries=settings.SETTINGS.cache_entries,
        artifact_path=settings.SETTINGS.state_db.with_name('access-cache.sqlite3'))
    while not STOP:
        if not run_once(store):time.sleep(.4)


if __name__=='__main__':main()
