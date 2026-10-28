"""Rebuildable, compressed accessibility artifacts shared by web and worker.

Keys contain hashes of every geographic input. Cached resident indices therefore
cannot be reused against another population ordering or pedestrian network.
"""
import hashlib
import json
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path


def fingerprint(directory):
    digest=hashlib.sha256(b'access-artifact-v1')
    for name in ('census.geojson','buildings.geojson','walkways.geojson','population_anchors.json'):
        digest.update(name.encode())
        path=Path(directory)/name
        if path.is_file():
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


class AccessCache:
    def __init__(self,path,namespace):
        self.path=Path(path);self.namespace=namespace
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS access_artifacts(namespace TEXT,key TEXT,value BLOB,PRIMARY KEY(namespace,key))')
            conn.commit()

    def connect(self):return sqlite3.connect(self.path,timeout=30)

    def get(self,key):
        with closing(self.connect()) as conn:
            row=conn.execute('SELECT value FROM access_artifacts WHERE namespace=? AND key=?',(self.namespace,key)).fetchone()
        if row is None:return None
        try:return json.loads(zlib.decompress(row[0]))
        except (ValueError,zlib.error):return None

    def put(self,key,value):
        payload=zlib.compress(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode(),3)
        with closing(self.connect()) as conn:
            conn.execute('INSERT OR REPLACE INTO access_artifacts VALUES (?,?,?)',(self.namespace,key,payload));conn.commit()
