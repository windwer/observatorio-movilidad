"""One-command attempt to obtain every freely reachable source; logs failures.

Run on your own connected PC: python bootstrap_sources.py
It imports CURRENT schedules only; historical snapshots require original archives.
It does not guess missing census joins or fabricate historical/observed data.
"""
from pathlib import Path
from datetime import date, datetime
import argparse
import json
import traceback
import source_fetch
import engine
import territory

ROOT=Path(__file__).resolve().parent

def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('--skip-osm',action='store_true',help='Skip potentially slow Overpass downloads')
    args.add_argument('--skip-references',action='store_true')
    args=args.parse_args()
    base=ROOT/'data';base.mkdir(parents=True,exist_ok=True)
    con=engine.connect(base/'observatorio.sqlite3')
    store=territory.TerritoryStore(base/'geography')
    records=[]
    def attempt(label,func):
        print('→',label,flush=True)
        try:
            result=func();row={'source':label,'status':'downloaded','result':result}
            print('  OK',str(result)[:180],flush=True)
        except Exception as e:
            row={'source':label,'status':'unavailable','error':str(e)}
            print('  NO DISPONIBLE:',str(e)[:300],flush=True)
        records.append(row)
        (base/'acquisition_manifest.json').write_text(json.dumps({
          'run_at':datetime.now().isoformat(),'historical_cutoff':engine.CUTOFF.isoformat(),
          'historical_certification':False,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        for op in ('ekialdebus','irunbus'):
            def gtfs(op=op):
                raw=source_fetch.fetch_gtfs(op)
                return engine.ingest(con,raw,op,date.today().isoformat(),op+'_current_NAP_mirror.zip')
            attempt('current_gtfs_'+op,gtfs)
        if not args.skip_references:
            for name in ('eustat_csv','census_geometry'):
                def reference(name=name):
                    ext='.csv' if name=='eustat_csv' else '.zip'
                    return source_fetch.fetch_reference(name,base/'references'/(name+ext))
                attempt(name,reference)
        if not args.skip_osm:
            attempt('osm_pedestrian_network',lambda:store.ingest('walkways',source_fetch.fetch_osm_walkways()))
            attempt('osm_residential_buildings',lambda:store.ingest('buildings',source_fetch.fetch_osm_buildings()))
    finally:con.close()
    print('\nInforme:',base/'acquisition_manifest.json')
    print('AVISO: se requiere unir censos y geometría, y conseguir las versiones de GTFS de 2025-18/10/2026.')

if __name__=='__main__':main()
