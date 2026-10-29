"""A cheap, shared identity for published data and mutable staging snapshots."""
import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path
import model
from access_cache import fingerprint

_CACHE=OrderedDict();_LOCK=threading.Lock()

def identity(db,geography,release_id,cutoff):
    db=Path(db).resolve();geography=Path(geography).resolve()
    paths=[db,Path(str(db)+'-wal'),db.parent/'release-manifest.json']
    paths.extend(geography/name for name in ('census.geojson','walkways.geojson','buildings.geojson','population_anchors.json'))
    stamps=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths if p.is_file())
    key=(stamps,release_id,str(cutoff),model.signature())
    with _LOCK:
        if key in _CACHE:return _CACHE[key]
        payload={'files':stamps,'release':release_id,'cutoff':str(cutoff),
                 'geography':fingerprint(geography),'method':model.signature()}
        value=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        _CACHE[key]=value
        while len(_CACHE)>8:_CACHE.popitem(last=False)
        return value
