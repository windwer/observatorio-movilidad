"""CI-only Docker rehearsal using small synthetic fixtures, never production data."""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,data_release
from test_engine import sample_gtfs
from test_territory import collection,feat,coord,square


def main():
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);source=root/'source.sqlite3';geo=root/'geo';geo.mkdir()
        conn=engine.connect(source);engine.ingest(conn,sample_gtfs(),'irunbus','2026-09-30','sample.zip')
        conn.execute('CREATE TABLE population_reference_meta(total INTEGER)');conn.execute('INSERT INTO population_reference_meta VALUES (10)');conn.commit();conn.close()
        (geo/'census.geojson').write_bytes(collection([feat({'type':'Polygon','coordinates':[square(0,0,500)]},municipality='Irun',population=10,section_id='a')]))
        (geo/'walkways.geojson').write_bytes(collection([feat({'type':'LineString','coordinates':[coord(0,0),coord(300,0)]},highway='footway')]))
        release=root/'release';data_release.build(source,geo,root/'missing.csv',release,'ci')
        docker('build','-t','observatorio-ci','.')
        env=['-e','OBS_ADMIN_PASSWORD=ci_only_secret_with_more_than_24_chars','-e','OBS_DB=/srv/observatorio/runtime/observatorio_real.sqlite3','-e','OBS_GEOGRAPHY_DIR=/srv/observatorio/runtime/geography','-e','OBS_STATE_DB=/srv/observatorio/state/state.sqlite3','-e','OBS_IMMUTABLE_DATA=1']
        common=[*env,'-v',str(release)+':/srv/observatorio/runtime:ro','-v','observatorio-ci-state:/srv/observatorio/state']
        names=[]
        try:
            for name,command in [('observatorio-ci-web',['python','app.py']),('observatorio-ci-worker',['python','worker.py'])]:
                args=['run','-d','--name',name,*common]
                if name.endswith('web'):args+=['-p','127.0.0.1:18874:8000']
                docker(*args,'observatorio-ci',*command);names.append(name)
            base='http://127.0.0.1:18874'
            def get(path):
                with urllib.request.urlopen(base+path,timeout=5) as response:return json.load(response)
            deadline=time.monotonic()+90
            while True:
                try:
                    if get('/api/health')['version']=='1.3.0':break
                except OSError:pass
                if time.monotonic()>deadline:raise AssertionError('Web not ready')
                time.sleep(1)
            while True:
                try:docker('exec','observatorio-ci-worker','python','worker.py','--healthcheck');break
                except subprocess.CalledProcessError:
                    if time.monotonic()>deadline:raise AssertionError('Worker not ready')
                    time.sleep(.5)
            request=urllib.request.Request(base+'/api/tasks',data=json.dumps({'kind':'compare_routes','operator':'irunbus','day':'2026-10-16','old_day':'2026-10-15','new_day':'2026-10-16'}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:job=json.load(response)
            while job['status'] in ('pending','running'):
                if time.monotonic()>deadline:raise AssertionError('Worker timeout')
                time.sleep(.5);job=get('/api/analysis/jobs/'+job['id'])
            assert job['status']=='complete',job
            docker('exec','observatorio-ci-worker','python','worker.py','--healthcheck')
        finally:
            for name in names:
                try:docker('rm','-f',name)
                except subprocess.CalledProcessError:pass
            docker('volume','rm','observatorio-ci-state')


if __name__=='__main__':main()
