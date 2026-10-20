"""Bulk import original GTFS ZIPs using a reviewable provenance manifest.

Usage: python import_sources.py --manifest path/to/sources.json
Manifest shape: {"versions":[{"operator":"ekialdebus", "snapshot_date":"2025-10-01",
                            "path":"ekialdebus_2025_10_01.zip", "sha256":"optional"}]}
Original ZIP bytes are preserved; importing never marks historical dates as verified.
"""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import engine

def import_manifest(conn,path):
    manifest=Path(path).resolve()
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    versions=data.get('versions')
    if not isinstance(versions,list) or not versions:raise ValueError('Manifest sin lista de versiones')
    if len(versions)>1000:raise ValueError('Demasiadas versiones en un solo manifiesto')
    results=[]
    for i,item in enumerate(versions):
        try:
            if not isinstance(item,dict):raise ValueError('Fila no es objeto JSON')
            operator=item['operator'];snapshot=engine.clean_date(item['snapshot_date'])
            raw_path=Path(item['path'])
            if not str(raw_path).endswith('.zip'):raise ValueError('Se requiere .zip')
            file=(manifest.parent/raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()
            if not file.is_file():raise ValueError('No se encontró el ZIP '+str(file))
            if file.stat().st_size>90_000_000:raise ValueError('Archivo ZIP supera 90 MB')
            raw=file.read_bytes();sha256=hashlib.sha256(raw).hexdigest()
            if item.get('sha256') and item['sha256'].lower()!=sha256:raise ValueError('SHA-256 no coincide')
            if item.get('sha1') and item['sha1'].lower()!=hashlib.sha1(raw).hexdigest():raise ValueError('SHA-1 no coincide')
            result=engine.ingest(conn,raw,operator,snapshot,file.name)
            results.append({'index':i,'state':'already_imported' if result['already_imported'] else 'imported',
               'operator':operator,'file':file.name,'snapshot_date':snapshot,'feed_id':result['feed_id'],'sha256':sha256})
        except (KeyError,ValueError,OSError,TypeError) as e:
            results.append({'index':i,'state':'error','reason':str(e)[:300]})
    return {'versions_listed':len(versions),'imported':sum(r['state']=='imported' for r in results),
        'failed':sum(r['state']=='error' for r in results),'items':results,
        'historical_certification':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--db',default='data/observatorio.sqlite3')
    options=parser.parse_args()
    conn=engine.connect(options.db)
    try:print(json.dumps(import_manifest(conn,options.manifest),ensure_ascii=False,indent=2))
    finally:conn.close()
if __name__=='__main__':main()
