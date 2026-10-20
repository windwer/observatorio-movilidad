"""Authorized Transitland historical GTFS downloader and importer.

Requires a user-provided key with access to historical archives (no circumvention).
Never modifies the frozen 2026-10-18 historical cut-off or marks data verified.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import engine

FEEDS={'ekialdebus':'f-lurraldebus~ekialdebus','irunbus':'f-lurraldebus~auif'}
BASE='https://transit.land/api/v2/rest'


def request(url,key,limit=120_000_000):
    if not key:raise ValueError('Falta TRANSITLAND_API_KEY con permisos de archivo histórico')
    if not url.startswith(BASE+'/'):raise ValueError('URL de archivo no autorizada')
    req=urllib.request.Request(url,headers={'apikey':key,'Accept':'application/json, application/zip','User-Agent':'GipuzkoaObservatory/0.3 (private non-automated batch)'})
    try:
        with urllib.request.urlopen(req,timeout=55) as res:
            payload=res.read(limit+1)
    except urllib.error.HTTPError as e:
        if e.code in (401,403):raise PermissionError('Tu API key no tiene permisos de descarga histórica en Transitland (401/403)') from e
        raise
    if len(payload)>limit:raise ValueError('Respuesta excesivamente grande')
    return payload


def archived_versions(operator,key,limit=1000):
    if operator not in FEEDS:raise ValueError('Operador no admitido')
    name=urllib.parse.quote(FEEDS[operator],safe='~')
    url=f'{BASE}/feeds/{name}/feed_versions?limit={min(int(limit),1000)}'
    obj=json.loads(request(url,key,limit=15_000_000))
    if not isinstance(obj,dict) or not isinstance(obj.get('feed_versions'),list):
        raise ValueError('Respuesta de catálogo inesperada; revisa permisos y documentación de Transitland')
    matches=[]
    for item in obj['feed_versions']:
        if not isinstance(item,dict):continue
        sha=item.get('sha1')
        fetched=str(item.get('fetched_at',''))[:10]
        start=str(item.get('earliest_calendar_date',''))[:10]
        end=str(item.get('latest_calendar_date',''))[:10]
        if not sha or len(sha)!=40 or not fetched or not start or not end:continue
        if fetched<=engine.CUTOFF.isoformat() and start<=engine.CUTOFF.isoformat() and end>='2025-01-01':
            matches.append({'sha1':sha,'fetched_at':fetched,'start':start,'end':end})
    matches.sort(key=lambda v:(v['fetched_at'],v['sha1']))
    return {'operator':operator,'selected_versions':matches,'returned_count':len(obj['feed_versions']),
        'catalogue_may_be_paginated':len(obj['feed_versions'])>=limit,
        'notice':'El catálogo no acredita la descarga, la importación ni la validación de las versiones.'}


def synchronize(operator,key,db_path,max_versions=5,dry_run=False,delay=1.0):
    catalog=archived_versions(operator,key)
    candidates=catalog['selected_versions']
    conn=engine.connect(db_path)
    results=[]
    try:
        for record in candidates[:max_versions]:
            if dry_run:
                results.append({**record,'state':'identified_not_downloaded'});continue
            sha=record['sha1']
            url=f'{BASE}/feed_versions/{sha}/download'
            try:
                content=request(url,key)
                digest=hashlib.sha1(content).hexdigest()
                if digest.lower()!=sha.lower():
                    raise ValueError('SHA-1 no coincide con el original archivado')
                result=engine.ingest(conn,content,operator,record['fetched_at'],
                              f'transitland-archived-{record["fetched_at"]}-{sha[:12]}.zip')
                results.append({**record,'state':'imported','feed_id':result['feed_id'],
                    'already_imported':result['already_imported']})
            except (ValueError,OSError,PermissionError,urllib.error.URLError) as e:
                results.append({**record,'state':'error','message':str(e)[:350]})
                if isinstance(e,PermissionError):break
            if delay>0:time.sleep(delay)
    finally:conn.close()
    return {**{k:v for k,v in catalog.items() if k!='selected_versions'},
        'examined':len(results),'results':results,
        'notice':'Los archivos descargados quedan sin certificar hasta comprobar calendarios y correspondencias oficiales.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operator',choices=tuple(FEEDS)+('both',),default='both')
    parser.add_argument('--db',default='data/observatorio.sqlite3')
    parser.add_argument('--max-versions',type=int,default=5,help='Límite por operador; evita descargas masivas accidentales')
    parser.add_argument('--dry-run',action='store_true',help='Solo mostrar el catálogo y las fechas sin descargar ZIP')
    args=parser.parse_args()
    if not 1<=args.max_versions<=200:parser.error('--max-versions debe estar entre 1 y 200')
    key=os.environ.get('TRANSITLAND_API_KEY','')
    if not key:parser.error('Define TRANSITLAND_API_KEY con acceso al archivo histórico (no lo incluyas en el ZIP)')
    outs=[]
    for op in FEEDS if args.operator=='both' else (args.operator,):
        outs.append(synchronize(op,key,args.db,args.max_versions,args.dry_run))
    print(json.dumps(outs,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
