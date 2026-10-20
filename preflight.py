"""Offline publication preflight. Data-gate failure is non-zero only with --strict."""
import argparse
import json
from pathlib import Path
import engine,audit,territory


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='data/observatorio.sqlite3')
    p.add_argument('--strict',action='store_true',help='Return nonzero when historical/geographic release gates fail')
    opts=p.parse_args()
    con=engine.connect(opts.db)
    try:
        geo=territory.TerritoryStore(Path(opts.db).parent/'geography')
        result=audit.readiness(con,geo.status())
        result['original_zip_count']=len(list((Path(opts.db).parent/'originals').glob('*.zip')))
        result['versions_imported']=len(engine.versions(con))
    finally:con.close()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('DECISIÓN: '+('DATOS VERIFICADOS, revisión de publicación aún requerida' if result['data_gate_passed'] else 'NO PUBLICAR: faltan datos o validación'))
    if opts.strict and not result['data_gate_passed']:raise SystemExit(2)

if __name__=='__main__':main()
