"""Offline staging and atomic activation; never edit a published release.

stage -> import_sources.py / local administration -> data_release.py build -> activate.
The serve supervisor restarts web and worker together when the pointer changes.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
import data_release


def write_pointer(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    with pending.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,path)


def activate(release,pointer,state_db):
    checked=data_release.validate(release)
    previous=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else None
    value={'release_dir':str(release.resolve()),'state_db':str(state_db.resolve()),'activation_id':uuid.uuid4().hex}
    if previous and (previous['release_dir']!=value['release_dir'] or previous['state_db']!=value['state_db']):
        write_pointer(pointer.with_suffix('.previous.json'),previous)
    write_pointer(pointer,value)
    return checked


def rollback(pointer):
    previous=pointer.with_suffix('.previous.json')
    if not previous.exists():raise ValueError('No hay una activación anterior')
    value=json.loads(previous.read_text(encoding='utf-8'))
    return activate(Path(value['release_dir']),pointer,Path(value['state_db']))


def stage(release,destination):
    # Verified restore makes a separate editable working copy; original remains immutable.
    result=data_release.restore(release,destination)
    (destination/'release-manifest.json').unlink()
    return result


def backup(release,state_db,destination):
    if destination.exists():raise FileExistsError('El destino de backup ya existe')
    data_release.restore(release,destination/'release')
    if state_db.is_file():data_release.sqlite_backup(state_db,destination/'state.sqlite3')
    files={p.relative_to(destination).as_posix():data_release.digest(p) for p in destination.rglob('*') if p.is_file()}
    write_pointer(destination/'backup.json',{'files':files})
    return {'backup':str(destination.resolve()),'files':len(files)}


def restore_backup(source,destination):
    metadata=json.loads((source/'backup.json').read_text(encoding='utf-8'))
    if not metadata.get('files'):raise ValueError('Backup sin manifiesto')
    for name,expected in metadata['files'].items():
        file=(source/name).resolve()
        if not file.is_relative_to(source.resolve()) or data_release.digest(file)!=expected:raise ValueError('Backup corrupto')
    data_release.restore(source/'release',destination/'release')
    if (source/'state.sqlite3').is_file():data_release.sqlite_backup(source/'state.sqlite3',destination/'state.sqlite3')
    return {'restored_to':str(destination.resolve())}


def serve(pointer,port):
    import urllib.request
    import base64
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    processes=[];stamp=None
    def shutdown():
        for process in processes:
            if process.poll() is None:process.terminate()
        for process in processes:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        processes.clear()
    try:
        while not stopped:
            current=pointer.read_bytes()
            if current!=stamp:
                data=json.loads(current);data_release.validate(Path(data['release_dir']))
                shutdown()
                env=os.environ.copy()
                env.update(OBS_ACTIVE_RELEASE_FILE=str(pointer.resolve()),OBS_IMMUTABLE_DATA='1',OBS_HOST='127.0.0.1',OBS_PORT=str(port))
                for name in ('OBS_DB','OBS_GEOGRAPHY_DIR','OBS_STATE_DB','OBS_REFERENCE_CSV'):env.pop(name,None)
                for script in ('app.py','worker.py'):
                    processes.append(subprocess.Popen([sys.executable,script],cwd=Path(__file__).parent,env=env))
                deadline=time.monotonic()+120;healthy=False
                while time.monotonic()<deadline and not stopped and all(p.poll() is None for p in processes):
                    try:
                        request=urllib.request.Request(f'http://127.0.0.1:{port}/api/ready')
                        password=env.get('OBS_READER_PASSWORD') or env.get('OBS_PASSWORD')
                        if password:
                            credentials=env.get('OBS_READER_USERNAME','analista')+':'+password
                            request.add_header('Authorization','Basic '+base64.b64encode(credentials.encode()).decode())
                        with urllib.request.urlopen(request,timeout=2) as response:
                            status=json.load(response)
                        if status.get('analysis_ready'):healthy=True;break
                    except (OSError,ValueError):pass
                    time.sleep(.5)
                if not healthy:
                    shutdown()
                    if stamp is not None:
                        write_pointer(pointer,json.loads(stamp));current=stamp;stamp=None;continue
                    raise RuntimeError('La versión no supera la comprobación de arranque')
                stamp=current
            if any(p.poll() is not None for p in processes):
                shutdown();stamp=None
            time.sleep(.5)
    finally:shutdown()


def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='action',required=True)
    create=commands.add_parser('stage');create.add_argument('release',type=Path);create.add_argument('destination',type=Path)
    publish=commands.add_parser('activate');publish.add_argument('release',type=Path);publish.add_argument('pointer',type=Path);publish.add_argument('--state-db',type=Path,required=True)
    undo=commands.add_parser('rollback');undo.add_argument('pointer',type=Path)
    run=commands.add_parser('serve');run.add_argument('pointer',type=Path);run.add_argument('--port',type=int,default=8874)
    save=commands.add_parser('backup');save.add_argument('release',type=Path);save.add_argument('destination',type=Path);save.add_argument('--state-db',type=Path,required=True)
    recover=commands.add_parser('restore-backup');recover.add_argument('source',type=Path);recover.add_argument('destination',type=Path)
    args=parser.parse_args()
    if args.action=='stage':result=stage(args.release,args.destination)
    elif args.action=='activate':result=activate(args.release,args.pointer,args.state_db)
    elif args.action=='rollback':result=rollback(args.pointer)
    elif args.action=='backup':result=backup(args.release,args.state_db,args.destination)
    elif args.action=='restore-backup':result=restore_backup(args.source,args.destination)
    else:serve(args.pointer,args.port);return
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
