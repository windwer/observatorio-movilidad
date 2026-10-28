"""Bounded read-only load rehearsal for a local or staging observatory."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PATHS=(
    '/api/health',
    '/api/version',
    '/api/month?operator=irunbus&year=2026&month=10&day_type=LJ&hour_start=0&hour_end=2880',
    '/api/map?operator=irunbus&day=2026-10-16',
    '/api/routes?operator=irunbus&year=2026&month=10',
)


def percentile(values,percent):
    if not values:return None
    ordered=sorted(values);position=max(0,min(len(ordered)-1,math.ceil(len(ordered)*percent)-1))
    return ordered[position]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8873')
    parser.add_argument('--sessions',type=int,default=20)
    parser.add_argument('--seconds',type=int,default=900)
    parser.add_argument('--timeout',type=float,default=10)
    parser.add_argument('--think-ms',type=float,default=500,help='Pausa entre acciones de cada sesión')
    parser.add_argument('--p95-budget-ms',type=float,default=1000)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--mixed',action='store_true',help='Incluye operadores, periodos, frecuencias e isócronas distintos')
    args=parser.parse_args()
    paths=list(PATHS)
    if args.mixed:
        for operator in ('irunbus','ekialdebus','euskotren','errenteria_urbanoa'):
            for year,day_type in ((2025,'LJ'),(2026,'S')):
                paths.append(f'/api/month?operator={operator}&year={year}&month=10&day_type={day_type}')
            path=f'/api/map?operator={operator}&day=2026-10-22'
            paths.append(path)
            with urllib.request.urlopen(args.base+path,timeout=60) as response:data=json.load(response)
            if data.get('routes'):
                route=urllib.parse.quote(str(data['routes'][0]['id']),safe='')
                paths.extend([f'/api/route/metrics?operator={operator}&route_id={route}&day=2026-10-22',
                              f'/api/route/frequency?operator={operator}&route_id={route}&day=2026-10-22&year=2026&month=10'])
            if data.get('stops'):
                stop=urllib.parse.quote(str(data['stops'][0]['id']),safe='')
                paths.extend(f'/api/geo/stop?operator={operator}&day=2026-10-22&stop_id={stop}&minutes={minutes}' for minutes in (5,10))
    if not 1<=args.sessions<=100 or not 5<=args.seconds<=3600 or not 0<=args.think_ms<=10000:
        raise SystemExit('Límites de ensayo inválidos')
    deadline=time.monotonic()+args.seconds;lock=threading.Lock();latencies=[];errors=[];counts={}

    def session(number):
        index=number
        while time.monotonic()<deadline:
            path=paths[index%len(paths)];index+=1;started=time.perf_counter()
            try:
                with urllib.request.urlopen(args.base+path,timeout=args.timeout) as response:
                    response.read();status=response.status
                if status!=200:raise RuntimeError(f'HTTP {status}')
                elapsed=(time.perf_counter()-started)*1000
                with lock:latencies.append(elapsed);counts[path]=counts.get(path,0)+1
            except Exception as exc:
                with lock:errors.append({'path':path,'error':f'{type(exc).__name__}: {exc}'})
            remaining=deadline-time.monotonic()
            if remaining>0 and args.think_ms:
                time.sleep(min(remaining,args.think_ms/1000))

    started=time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.sessions) as pool:
        list(pool.map(session,range(args.sessions)))
    result={'base':args.base,'sessions':args.sessions,'distinct_paths':len(paths),'duration_seconds':round(time.time()-started,1),
            'requests':len(latencies),'errors':len(errors),'counts':counts,
            'latency_ms':{'average':round(statistics.mean(latencies),1) if latencies else None,
                          'p50':round(percentile(latencies,.50),1) if latencies else None,
                          'p95':round(percentile(latencies,.95),1) if latencies else None,
                          'maximum':round(max(latencies),1) if latencies else None},
            'error_examples':errors[:10]}
    rendered=json.dumps(result,ensure_ascii=False,indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered+'\n',encoding='utf-8')
    if errors or not latencies or result['latency_ms']['p95']>args.p95_budget_ms:raise SystemExit(1)


if __name__=='__main__':main()
