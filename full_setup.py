"""Reproducible acquisition, historical import and audit pipeline for a connected local PC.

It deliberately never certifies absent or future service and never publishes.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import engine,audit,data_quality,territory

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-osm',action='store_true',help='Evita Overpass, normalmente más lento')
    parser.add_argument('--archive-limit',type=int,default=100)
    parser.add_argument('--no-download',action='store_true')
    parser.add_argument('--historical-manifest',help='Manifiesto local de GTFS ZIP originales')
    parser.add_argument('--census-config',help='Config JSON de claves oficiales GeoEuskadi/Eustat')
    options=parser.parse_args()
    data=ROOT/'data';data.mkdir(parents=True,exist_ok=True)
    results=[]
    def run(label,args):
        print('\n>>> '+label,flush=True)
        try:
            proc=subprocess.run([sys.executable,*args],cwd=ROOT,timeout=1500,check=False)
            results.append({'task':label,'returncode':proc.returncode})
        except (OSError,subprocess.TimeoutExpired) as error:
            results.append({'task':label,'error':str(error)})
    if not options.no_download:
        args=['bootstrap_sources.py']
        if options.skip_osm:args.append('--skip-osm')
        run('Fuentes actuales, censo y OSM',args)
    if os.environ.get('TRANSITLAND_API_KEY'):
        run('Archivo histórico con autorización',['archive_sync.py','--operator','both','--max-versions',str(options.archive_limit)])
    else:
        results.append({'task':'archivo_historico','state':'pending_authorized_access',
            'action':'Solicita ZIP históricos oficiales o define TRANSITLAND_API_KEY con permisos adecuados.'})
    if options.historical_manifest:
        run('Importación histórica local',['import_sources.py','--manifest',options.historical_manifest])
    pop_file=data/'references'/'eustat_csv.csv'
    normalized=data/'references'/'eustat_sections_normalized.csv'
    if pop_file.exists():
        run('Normalizar tabla Eustat 2025',['normalize_eustat.py','--input',str(pop_file),'--output',str(normalized)])
    if options.census_config:
        try:
            import prepare_census
            spec=json.loads(Path(options.census_config).read_text(encoding='utf-8'))
            output=data/'geography'/'census.geojson'
            merged=prepare_census.merge(
                data/'references'/'census_geometry.zip',normalized,
                spec['geometry_keys'],spec.get('population_keys',['municipality_code','district','section']),
                spec.get('people_column','population'),spec.get('municipality_column','municipality'),output)
            store=territory.TerritoryStore(data/'geography')
            imported=store.ingest('census',output.read_bytes())
            results.append({'task':'censo_georreferenciado','state':'imported_unverified',
              'merge':merged,'import':imported})
        except Exception as e:
            results.append({'task':'censo_georreferenciado','state':'failed','reason':str(e)[:300]})
    conn=engine.connect(data/'observatorio.sqlite3')
    try:
        quality=data_quality.validate_all(conn)
        geography=territory.TerritoryStore(data/'geography').status()
        gate=audit.readiness(conn,geography)
        report={'generated_at':datetime.now(timezone.utc).isoformat(),
                'release':'0.5.1','historical_cutoff':'2026-10-18','process':results,
                'structural_quality':quality,'geographic_status':geography,'publication_gate':gate}
    finally:conn.close()
    path=data/'full_setup_report.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nInforme de preparación: '+str(path))
    print('Resultado: '+('DATOS COTEJADOS; aún requiere autorización de publicación' if gate['data_gate_passed'] else 'NO PUBLICAR: faltan datos o certificaciones'))
    return report

if __name__=='__main__':main()
