"""Prepare exact 5/10-minute stop artifacts, resumably, outside request serving."""
import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from territory import TerritoryStore


def prepare(db,geography,cache,limit=0):
    started=time.perf_counter()
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        stops=conn.execute('''SELECT DISTINCT ROUND(lat,6),ROUND(lon,6) FROM stops
            WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY 1,2''').fetchall()
    if limit:stops=stops[:limit]
    store=TerritoryStore(geography,artifact_path=cache)
    print(json.dumps({'event':'start','unique_stops':len(stops)}),flush=True)
    for number,(lat,lon) in enumerate(stops,1):
        for minutes in (5,10):
            store.reachable(lat,lon,minutes)
            store.stop(lat,lon,minutes=minutes)
        if number%25==0 or number==len(stops):
            print(json.dumps({'done':number,'total':len(stops),'seconds':round(time.perf_counter()-started,1),
                              'cache':store.cache_status()}),flush=True)
    return {'stops':len(stops),'thresholds':[5,10],'seconds':round(time.perf_counter()-started,1)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--geography',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args()
    prepare(args.db,args.geography,args.cache,args.limit)


if __name__=='__main__':main()
