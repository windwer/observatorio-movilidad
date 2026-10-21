"""Launch a private local instance on a port free from older Observatory versions.

Always open the *actual* running version instead of reusing a stale 8000 tab.
"""
import json
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

VERSION='1.0'
ROOT=Path(__file__).resolve().parent

def free_port():
    requested=int(os.environ.get('OBS_PORT','8765'))
    if not 1024<=requested<=65535:raise ValueError('Puerto inválido')
    for port in range(requested,min(requested+35,65536)):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))!=0:
                return port
    raise RuntimeError('No hay un puerto libre entre %s y %s'%(requested,requested+34))

def get_json(url, env, timeout=3):
    request=urllib.request.Request(url)
    if env.get('OBS_PASSWORD'):
        credentials=f"{env.get('OBS_USERNAME','analista')}:{env['OBS_PASSWORD']}"
        request.add_header('Authorization','Basic '+base64.b64encode(credentials.encode()).decode())
    with urllib.request.urlopen(request,timeout=timeout) as resp:
        if resp.status!=200:raise RuntimeError(f'HTTP {resp.status} en {url}')
        return json.load(resp)

def validate_real_package(port, env):
    """Refuse to open an empty/old runtime as if it were the real package."""
    if env.get('OBS_DEMO')=='1':return
    requirements=get_json(f'http://127.0.0.1:{port}/api/data/requirements',env)
    missing={'euskotren','errenteria_urbanoa'}-set(requirements.get('operators',[]))
    if missing:raise RuntimeError('Faltan operadores en la instancia: '+', '.join(sorted(missing)))
    population=get_json(f'http://127.0.0.1:{port}/api/population/status',env)
    if population.get('total_population')!=150832 or not population.get('spatial_coverage_ready'):
        raise RuntimeError('La instancia no tiene cargada la población Eustat/geometría censal de v1')
    geography=get_json(f'http://127.0.0.1:{port}/api/geo/status',env)
    if geography.get('census_sections',0)<109 or geography.get('walk_segments',0)<=0:
        raise RuntimeError('La instancia no tiene la geografía real necesaria para población/isócronas')

def main():
    port=free_port()
    env=os.environ.copy();env['OBS_HOST']='127.0.0.1';env['OBS_PORT']=str(port)
    url=f'http://127.0.0.1:{port}/?v={VERSION}'
    process=subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT,env=env)
    try:
        for _ in range(80):
            if process.poll() is not None:raise RuntimeError('El servidor terminó inesperadamente; consulta la consola')
            try:
                payload=get_json(f'http://127.0.0.1:{port}/api/health',env,timeout=.7)
                if payload.get('version')!=VERSION:raise RuntimeError('La versión del servidor no corresponde al paquete')
                break
            except (OSError,TimeoutError):time.sleep(.25)
        else:raise RuntimeError('El servidor no respondió correctamente')
        validate_real_package(port,env)
        print('\n'+'='*60,flush=True)
        print('OBSERVATORIO '+VERSION+' · CORTE HISTÓRICO 18/10/2026',flush=True)
        print('Dirección confirmada: '+url,flush=True)
        print('No uses pestañas antiguas de http://127.0.0.1:8000',flush=True)
        print('='*60+'\n',flush=True)
        webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()

if __name__=='__main__':main()
