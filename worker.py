"""Single-purpose local worker for durable geographic analysis jobs."""
from __future__ import annotations

import json
import signal
import time
import multiprocessing
import queue
import os
import data_identity

import analysis_jobs
import engine
import settings
import territory


STOP=False


def _stop(*_args):
    global STOP;STOP=True


def _execute(inbox,output,executor=None):
    import threading
    parent=multiprocessing.parent_process()
    def watch_parent():
        while parent is not None:
            if not parent.is_alive():os._exit(1)
            time.sleep(1)
    threading.Thread(target=watch_parent,daemon=True).start()
    import tasks
    while True:
        kind,params=inbox.get()
        try:output.put(((executor or tasks.execute)(kind,params),None))
        except Exception as exc:output.put((None,f'{type(exc).__name__}: {exc}'))


def main(executor=None):
    signal.signal(signal.SIGINT,_stop);signal.signal(signal.SIGTERM,_stop)
    config=settings.SETTINGS
    identity=data_identity.identity(config.db,config.geography_dir,config.release_id,config.cutoff)
    worker_id=f'worker-{os.getpid()}'
    context=multiprocessing.get_context('spawn')
    analysis_jobs.prune(config.state_db,config.retention_days)
    cleanup_at=time.monotonic()+3600
    process=None;inbox=None;output=None
    while not STOP:
        identity=data_identity.identity(config.db,config.geography_dir,config.release_id,config.cutoff)
        if time.monotonic()>=cleanup_at:
            analysis_jobs.prune(config.state_db,config.retention_days);cleanup_at=time.monotonic()+3600
        analysis_jobs.heartbeat(config.state_db,worker_id,identity)
        row=analysis_jobs.claim(config.state_db,config.job_timeout_seconds,worker_id)
        if row is None:
            time.sleep(.4);continue
        params=json.loads(row['params_json'])
        if row['cache_key']!=analysis_jobs.make_cache_key(row['kind'],params,identity,settings.METHOD_VERSION):
            analysis_jobs.finish(config.state_db,row['id'],error='Los datos han cambiado; solicita de nuevo el cálculo',lease_token=row['lease_token'])
            continue
        if process is None or not process.is_alive():
            if inbox is not None:inbox.close();output.close()
            inbox=context.Queue(maxsize=1);output=context.Queue(maxsize=1)
            process=context.Process(target=_execute,args=(inbox,output,executor),daemon=True);process.start()
        inbox.put((row['kind'],params))
        deadline=time.monotonic()+config.job_timeout_seconds
        result=None;error=None;owned=True
        try:
            while True:
                analysis_jobs.heartbeat(config.state_db,worker_id,identity,'busy')
                if STOP or time.monotonic()>=deadline:
                    error='Trabajo interrumpido' if STOP else 'Tiempo máximo de cálculo superado';break
                if not analysis_jobs.renew(config.state_db,row['id'],row['lease_token']):
                    owned=False;break
                try:result,error=output.get(timeout=1);break
                except queue.Empty:
                    if not process.is_alive():error='El proceso de cálculo terminó sin resultado';break
        finally:
            if not owned or error or STOP:
                if process.is_alive():process.terminate()
                process.join(timeout=5)
        if owned:analysis_jobs.finish(config.state_db,row['id'],result=result,error=error,lease_token=row['lease_token'])
    if process is not None:
        if process.is_alive():process.terminate()
        process.join(timeout=5);inbox.close();output.close()


if __name__=='__main__':
    import sys
    if '--healthcheck' in sys.argv:
        config=settings.SETTINGS
        ident=data_identity.identity(config.db,config.geography_dir,config.release_id,config.cutoff)
        sys.exit(0 if analysis_jobs.worker_status(config.state_db,ident)['healthy'] else 1)
    main()
