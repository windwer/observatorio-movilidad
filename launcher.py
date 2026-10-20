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

VERSION='0.6.5'
ROOT=Path(__file__).resolve().parent

def free_port():
    requested=int(os.environ.get('OBS_PORT','8765'))
    if not 1024<=requested<=65535:raise ValueError('Puerto inválido')
    for port in range(requested,min(requested+35,65536)):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))!=0:
                return port
    raise RuntimeError('No hay un puerto libre entre %s y %s'%(requested,requested+34))

def main():
    port=free_port()
    env=os.environ.copy();env['OBS_HOST']='127.0.0.1';env['OBS_PORT']=str(port)
    url=f'http://127.0.0.1:{port}/?v={VERSION}'
    process=subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT,env=env)
    try:
        for _ in range(80):
            if process.poll() is not None:raise RuntimeError('El servidor terminó inesperadamente; consulta la consola')
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{port}/api/health')
                if env.get('OBS_PASSWORD'):
                    credentials=f"{env.get('OBS_USERNAME','analista')}:{env['OBS_PASSWORD']}"
                    request.add_header('Authorization','Basic '+base64.b64encode(credentials.encode()).decode())
                with urllib.request.urlopen(request,timeout=.7) as resp:
                    if resp.status==200:
                        payload=json.load(resp)
                        if payload.get('version')!=VERSION:raise RuntimeError('La versión del servidor no corresponde al paquete')
                        break
            except (OSError,TimeoutError):time.sleep(.25)
        else:raise RuntimeError('El servidor no respondió correctamente')
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
