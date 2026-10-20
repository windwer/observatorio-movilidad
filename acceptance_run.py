"""Auditoría reproducible del MVP privado.

Ejecutar: python acceptance_run.py
No introduce datos ni transforma planificación en histórico verificado.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parent

def validate():
    proc=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-q'],cwd=ROOT,text=True,capture_output=True,timeout=150)
    with tempfile.TemporaryDirectory(prefix='observatorio_acceptance_') as d:
        os.environ['OBS_DB']=str(Path(d)/'acceptance.sqlite3')
        os.environ['OBS_HOST']='127.0.0.1'
        os.environ.pop('OBS_PASSWORD',None)
        sys.path.insert(0,str(ROOT))
        import app,engine,audit
        client=TestClient(app.app)
        checks={}
        expected={
            '/':'text/html',
            '/static/app.js':'javascript',
            '/api/health':'application/json',
            '/api/version':'application/json',
            '/api/coverage?operator=ekialdebus&year=2025':'application/json',
            '/api/audit/readiness':'application/json',
            '/api/quality':'application/json',
            '/api/map/both?day=2026-10-16':'application/json',
        }
        for url,ctype in expected.items():
            r=client.get(url)
            checks[url]={'http':r.status_code,'ok':r.status_code==200,'content_type':r.headers.get('content-type','')}
        cut=client.get('/api/health').json()
        readiness=client.get('/api/audit/readiness').json()
        candidate=client.get('/api/map/both?day=2026-10-16').json()
        planned=client.get('/api/map/both?day=2026-10-19').json()
        checks['fixed_cutoff']={'ok':cut.get('cutoff')=='2026-10-18','actual':cut.get('cutoff')}
        checks['planning_boundary']={'ok':candidate.get('state')=='historical' and planned.get('state')=='planning',
          'oct18_historical':candidate.get('state'),'oct19_planning':planned.get('state')}
        checks['missing_not_zero']={'ok':candidate.get('quality')=='missing' and not candidate.get('routes'),
          'actual':candidate.get('quality')}
        checks['no_false_publication']={'ok':not readiness.get('publication_ready') and not readiness.get('data_gate_passed'),
          'reason':readiness.get('reasons',[])}
        checks['no_export']={'ok': 'id="export-button"' not in client.get('/').text.lower() and client.get('/api/download').status_code==404}
        return {
            'version':'0.5.1','date_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'historical_cutoff':'2026-10-18','official_sources_imported':False,
            'test_suite':{'passed':proc.returncode==0,'summary':(proc.stderr+proc.stdout).splitlines()[-3:],
                          'stderr_tail':proc.stderr[-2500:] if proc.returncode else ''},
            'http_and_semantics':checks,
            'historic_coverage':readiness.get('operators'),
            'geographic_ready':readiness.get('geographic_gate_passed'),
            'data_gate_passed':readiness.get('data_gate_passed'),
            'application_release_accepted':False,
            'blockers':['GTFS históricos oficiales completos y autorizados de los dos operadores',
               'Cotejo documental por fecha y calendario, incluido cambio de concesión de octubre de 2026',
               'Secciones y población Eustat 2025 cruzadas con edificios y red peatonal de los seis municipios',
               'Revisión manual de isócronas y de las diferencias espaciales y de oferta',
               'Validación UX/seguridad en navegador y entorno Windows de destino',
               'Aprobación privada final del proyecto'],
        }

if __name__=='__main__':
    result=validate()
    dest=ROOT/'ACCEPTANCE_EVIDENCE.json'
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'tests':result['test_suite']['summary'],'checks':sum(x['ok'] for x in result['http_and_semantics'].values()),
        'checks_total':len(result['http_and_semantics']),'data_gate_passed':result['data_gate_passed'],
        'accepted':result['application_release_accepted'],'evidence':str(dest)},ensure_ascii=False,indent=2))
    if not result['test_suite']['passed'] or not all(x['ok'] for x in result['http_and_semantics'].values()):sys.exit(1)
