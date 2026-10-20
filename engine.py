"""GTFS snapshot ingestion and reproducible calendar analysis.

Historical cut-off is frozen at 2026-10-18.  All results are scheduled
service, not proof that trips actually ran.
"""
from __future__ import annotations
import calendar as cal
import csv
import hashlib
import io
import json
import sqlite3
import statistics
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

CUTOFF = date(2026, 10, 18)
OPERATORS = {"ekialdebus": "Ekialdebus", "irunbus": "Irunbus"}
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS feeds (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, operator TEXT NOT NULL,
 snapshot_date TEXT NOT NULL, original_name TEXT NOT NULL,
 imported_at TEXT NOT NULL, min_date TEXT, max_date TEXT,
 route_count INT DEFAULT 0, stop_count INT DEFAULT 0, warning TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS routes (
 feed_id INT NOT NULL, route_id TEXT NOT NULL, short_name TEXT, long_name TEXT,
 PRIMARY KEY(feed_id,route_id)
);
CREATE TABLE IF NOT EXISTS stops (
 feed_id INT NOT NULL, stop_id TEXT NOT NULL, name TEXT,
 lat REAL, lon REAL, PRIMARY KEY(feed_id,stop_id)
);
CREATE TABLE IF NOT EXISTS services (
 feed_id INT NOT NULL, service_id TEXT NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 mon INT,tue INT,wed INT,thu INT,fri INT,sat INT,sun INT,
 PRIMARY KEY(feed_id,service_id)
);
CREATE TABLE IF NOT EXISTS exceptions (
 feed_id INT NOT NULL, service_id TEXT NOT NULL,
 service_date TEXT NOT NULL, exception_type INT NOT NULL,
 PRIMARY KEY(feed_id,service_id,service_date)
);
CREATE TABLE IF NOT EXISTS trips (
 feed_id INT NOT NULL, trip_id TEXT NOT NULL,route_id TEXT NOT NULL,
 service_id TEXT NOT NULL, direction_id TEXT, headsign TEXT, shape_id TEXT,
 PRIMARY KEY(feed_id,trip_id)
);
CREATE TABLE IF NOT EXISTS stop_times (
 feed_id INT NOT NULL, trip_id TEXT NOT NULL, stop_id TEXT NOT NULL,
 seq INT NOT NULL, dep_min INT, arr_min INT,
 PRIMARY KEY(feed_id,trip_id,seq)
);
CREATE TABLE IF NOT EXISTS shapes (
 feed_id INT NOT NULL,shape_id TEXT NOT NULL,seq INT NOT NULL,lat REAL,lon REAL,
 PRIMARY KEY(feed_id,shape_id,seq)
);
CREATE INDEX IF NOT EXISTS ix_feeds_lookup ON feeds(operator,min_date,max_date,snapshot_date);
CREATE INDEX IF NOT EXISTS ix_feeds_hash ON feeds(sha256,operator,snapshot_date);
CREATE INDEX IF NOT EXISTS ix_services_dates ON services(feed_id,start_date,end_date);
CREATE INDEX IF NOT EXISTS ix_exceptions ON exceptions(feed_id,service_date);
CREATE INDEX IF NOT EXISTS ix_trips_service ON trips(feed_id,service_id);
CREATE INDEX IF NOT EXISTS ix_stoptimes_trip ON stop_times(feed_id,trip_id);
CREATE INDEX IF NOT EXISTS ix_stoptimes_stop ON stop_times(feed_id,stop_id);
CREATE INDEX IF NOT EXISTS ix_shapes ON shapes(feed_id,shape_id,seq);
"""

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn=sqlite3.connect(path)
    conn.row_factory=sqlite3.Row
    conn.executescript(SCHEMA)
    migrate_feed_hash_constraint(conn)
    return conn

def migrate_feed_hash_constraint(conn):
    """Allow identical GTFS bytes to be kept for different capture dates.

    Older databases declared ``feeds.sha256`` UNIQUE, which erased a valid
    historical snapshot when two dated downloads had identical bytes. The
    migration preserves every feed id and child row while replacing that
    global uniqueness with a non-unique lookup index.
    """
    indexes=conn.execute('PRAGMA index_list(feeds)').fetchall()
    if not any(int(row['unique']) and str(row['name']).startswith('sqlite_autoindex') for row in indexes):
        return
    with conn:
        conn.execute('DROP INDEX IF EXISTS ix_feeds_lookup')
        conn.execute('ALTER TABLE feeds RENAME TO feeds_legacy_hash_unique')
        conn.execute('''CREATE TABLE feeds (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, operator TEXT NOT NULL,
 snapshot_date TEXT NOT NULL, original_name TEXT NOT NULL,
 imported_at TEXT NOT NULL, min_date TEXT, max_date TEXT,
 route_count INT DEFAULT 0, stop_count INT DEFAULT 0, warning TEXT DEFAULT ''
)''')
        conn.execute('''INSERT INTO feeds
 (id,sha256,operator,snapshot_date,original_name,imported_at,min_date,max_date,route_count,stop_count,warning)
 SELECT id,sha256,operator,snapshot_date,original_name,imported_at,min_date,max_date,route_count,stop_count,warning
 FROM feeds_legacy_hash_unique''')
        conn.execute('DROP TABLE feeds_legacy_hash_unique')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_feeds_lookup ON feeds(operator,min_date,max_date,snapshot_date)')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_feeds_hash ON feeds(sha256,operator,snapshot_date)')

def clean_date(s):
    s=(s or '').strip()
    if len(s)==8 and s.isdigit(): s=f'{s[:4]}-{s[4:6]}-{s[6:]}'
    return date.fromisoformat(s).isoformat()

def minutes(s):
    if not s: return None
    parts=s.split(':')
    try:
        if len(parts)!=3: return None
        h,m,sec=map(int,parts)
        if h<0 or h>48 or m<0 or m>59 or sec<0 or sec>59 or (h==48 and (m!=0 or sec!=0)): return None
        return h*60+m+sec/60
    except (ValueError, IndexError, TypeError): return None

def fmt_minutes(n):
    if n is None: return None
    total_secs=round(float(n)*60)
    hh,remaining=divmod(total_secs,3600)
    mm,ss=divmod(remaining,60)
    return f'{hh:02d}:{mm:02d}:{ss:02d}' if ss else f'{hh:02d}:{mm:02d}'

def safe_float(s):
    try: return float(s)
    except (ValueError,TypeError): return None

def read_gtfs(z,file):
    try: raw=z.read(file)
    except KeyError: return []
    txt=raw.decode('utf-8-sig',errors='replace')
    return list(csv.DictReader(io.StringIO(txt)))

def expand_exact_frequencies(data,frequencies):
    """Expand GTFS exact_times=1 only; fail closed for statistical headways.

    The application stores whole-minute precision. Reject any sub-minute pattern
    rather than silently rounding arrivals/departures.
    """
    by_trip=defaultdict(list)
    for i,row in enumerate(frequencies):
        if str(row.get('exact_times','0'))!='1':
            raise ValueError('frequencies.txt define frecuencias sin horas exactas (exact_times=0); no se puede reconstruir una tabla de salidas al minuto')
        try:headway=int(row.get('headway_secs','0'))
        except ValueError:raise ValueError('Frecuencia GTFS con headway_secs inválido')
        if not 60<=headway<=86400 or headway%60:
            raise ValueError('Frecuencia GTFS con intervalo no representable al minuto')
        def exact_minute(t):
            parts=str(t or '').split(':')
            if len(parts)!=3 or not parts[2].isdigit() or int(parts[2])!=0:
                raise ValueError('Frecuencia con segundos de salida no representables al minuto')
            value=minutes(t)
            if value is None:raise ValueError('frequencies.txt contiene hora inválida')
            return int(value)
        start=exact_minute(row.get('start_time'));end=exact_minute(row.get('end_time'))
        if end<=start:raise ValueError('frequencies.txt tiene una ventana vacía')
        by_trip[row['trip_id']].append((i,start,end,headway//60))
    trip_map={r['trip_id']:r for r in data['trips']}
    stops_by_trip=defaultdict(list)
    for row in data['stop_times']:stops_by_trip[row['trip_id']].append(row)
    new_trips=[];new_times=[]
    for trip in data['trips']:
        key=trip['trip_id'];patterns=by_trip.get(key)
        if not patterns:
            new_trips.append(trip);new_times.extend(stops_by_trip[key]);continue
        rows=sorted(stops_by_trip[key],key=lambda r:int(r['stop_sequence']))
        if not rows:raise ValueError('Plantilla GTFS de frecuencias sin paradas')
        base=minutes(rows[0].get('departure_time'))
        if base is None:raise ValueError('Plantilla GTFS de frecuencias sin salida de cabecera')
        for r in rows:
            for typ in ('arrival_time','departure_time'):
                t=r.get(typ)
                if t and (len(t.split(':'))!=3 or int(t.split(':')[-1])!=0):
                    raise ValueError('Plantilla GTFS de frecuencias con precisión de segundos no admitida')
        for i,start,end,step in patterns:
            for n,value in enumerate(range(start,end,step)):
                tid=f'{key}__exact_frequency_{i}_{n}'
                new_trips.append({**trip,'trip_id':tid})
                delta=value-base
                for row in rows:
                    shifted=dict(row);shifted['trip_id']=tid
                    for typ in ('arrival_time','departure_time'):
                        val=minutes(row.get(typ))
                        shifted[typ]=fmt_minutes(val+delta)+':00' if val is not None else ''
                    new_times.append(shifted)
                if len(new_trips)>750000 or len(new_times)>5000000:
                    raise ValueError('Expansión de frecuencias supera el límite de seguridad')
    unknown=set(by_trip)-set(trip_map)
    if unknown:raise ValueError('Plantillas en frequencies.txt sin trip_id existente')
    return {**data,'trips':new_trips,'stop_times':new_times}

def ingest(conn, content:bytes, operator:str, snapshot_date:str, filename:str):
    if operator not in OPERATORS: raise ValueError('Operador no permitido')
    snap=clean_date(snapshot_date)
    if date.fromisoformat(snap)>date.today():
        raise ValueError('La fecha de captura no puede ser futura')
    if len(content)>90_000_000: raise ValueError('GTFS supera el límite de 90 MB')
    digest=hashlib.sha256(content).hexdigest()
    # A captured GTFS with the same bytes on a different date is still a
    # distinct historical snapshot. Only the same operator/date/content is a
    # duplicate; otherwise the snapshot date would disappear from the index.
    existing=conn.execute('SELECT * FROM feeds WHERE sha256=? AND operator=? AND snapshot_date=?',(digest,operator,snap)).fetchone()
    if existing:
        return {"already_imported":True,"feed_id":existing['id'],"sha256":digest}
    foreign=conn.execute('SELECT * FROM feeds WHERE sha256=? AND operator<>? LIMIT 1',(digest,operator)).fetchone()
    if foreign: raise ValueError('Ese GTFS ya está asignado a otro operador')
    try: z=zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e: raise ValueError('No es un fichero ZIP válido') from e
    with z:
        if len(z.infolist())>60: raise ValueError('El ZIP GTFS contiene demasiados ficheros internos')
        names=set(z.namelist())
        required={'routes.txt','stops.txt','trips.txt','stop_times.txt'}
        if not required.issubset(names): raise ValueError('Faltan archivos GTFS: '+', '.join(sorted(required-names)))
        if any(i.file_size>100_000_000 for i in z.infolist()): raise ValueError('Archivo interno demasiado grande')
        if sum(i.file_size for i in z.infolist()) > 300_000_000: raise ValueError('GTFS descomprimido demasiado grande')
        data={s:read_gtfs(z,s+'.txt') for s in ['routes','stops','trips','stop_times','calendar','calendar_dates','shapes','feed_info']}
        # Preservar segundos GTFS sin truncarlos durante la conversión a minutos fraccionarios.
        for entry in data['stop_times']:
            for field in ('arrival_time','departure_time'):
                raw=entry.get(field,'')
                if raw and minutes(raw) is None:
                    raise ValueError(f'GTFS contiene {field} inválido: {raw!r}')
        # Exact-times frequency patterns can be enumerated as deterministic trips.
        # Non-exact patterns do not define departures and cannot become timetables.
        frequencies=read_gtfs(z,'frequencies.txt') if 'frequencies.txt' in names else []
        if frequencies:
            data=expand_exact_frequencies(data,frequencies)
    # Este MVP requiere GTFS con identificadores únicos por archivo.
    for table,key in (('routes','route_id'),('stops','stop_id'),('trips','trip_id'),('calendar','service_id')):
        ids=[r.get(key) for r in data[table]]
        if any(not x for x in ids) or len(ids)!=len(set(ids)):
            raise ValueError(f'{table}.txt contiene identificadores vacíos o duplicados')
    cal_dates=[]
    cal_dates += [clean_date(x['start_date']) for x in data['calendar'] if x.get('start_date')]
    cal_dates += [clean_date(x['end_date']) for x in data['calendar'] if x.get('end_date')]
    cal_dates += [clean_date(x['date']) for x in data['calendar_dates'] if x.get('date')]
    if cal_dates:
        low,high=min(cal_dates),max(cal_dates)
        warn = 'Sin calendar.txt; únicamente servicios de excepción' if not data['calendar'] else ''
    else:
        # Some historical planning snapshots are valid empty feeds: they carry
        # no routes or services but do publish their validity window in
        # feed_info.txt. Preserve that dated evidence instead of discarding it.
        info=data.get('feed_info') or []
        first_info=info[0] if info else {}
        try:
            low=clean_date(first_info.get('feed_start_date'))
            high=clean_date(first_info.get('feed_end_date'))
        except (TypeError,ValueError):
            raise ValueError('El feed no tiene calendario ni rango feed_info válido')
        warn = 'Feed GTFS vacío; rango tomado de feed_info.txt'
    with conn:
        cur=conn.execute('INSERT INTO feeds(sha256,operator,snapshot_date,original_name,imported_at,min_date,max_date,route_count,stop_count,warning) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (digest,operator,snap,filename,datetime.now().isoformat(timespec='seconds'),low,high,len(data['routes']),len(data['stops']),warn))
        fid=cur.lastrowid
        conn.executemany('INSERT INTO routes VALUES (?,?,?,?)',((fid,r['route_id'],r.get('route_short_name',''),r.get('route_long_name','')) for r in data['routes']))
        conn.executemany('INSERT INTO stops VALUES (?,?,?,?,?)',((fid,s['stop_id'],s.get('stop_name',''),safe_float(s.get('stop_lat')),safe_float(s.get('stop_lon'))) for s in data['stops']))
        conn.executemany('INSERT INTO services VALUES (?,?,?,?,?,?,?,?,?,?,?)',(
          (fid,r['service_id'],clean_date(r['start_date']),clean_date(r['end_date']),*(int(r.get(k,0)) for k in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'])) for r in data['calendar']))
        conn.executemany('INSERT OR REPLACE INTO exceptions VALUES (?,?,?,?)',((fid,r['service_id'],clean_date(r['date']),int(r['exception_type'])) for r in data['calendar_dates']))
        conn.executemany('INSERT INTO trips VALUES (?,?,?,?,?,?,?)',((fid,t['trip_id'],t['route_id'],t['service_id'],t.get('direction_id',''),t.get('trip_headsign',''),t.get('shape_id','')) for t in data['trips']))
        conn.executemany('INSERT INTO stop_times VALUES (?,?,?,?,?,?)',((fid,s['trip_id'],s['stop_id'],int(s['stop_sequence']),minutes(s.get('departure_time')),minutes(s.get('arrival_time'))) for s in data['stop_times']))
        conn.executemany('INSERT OR REPLACE INTO shapes VALUES (?,?,?,?,?)',((fid,s['shape_id'],int(s['shape_pt_sequence']),safe_float(s.get('shape_pt_lat')),safe_float(s.get('shape_pt_lon'))) for s in data['shapes']))
    # Preserve exact original ZIP bytes for reproducible, auditable analyses.
    db_path=conn.execute('PRAGMA database_list').fetchone()['file']
    if db_path:
        original_dir=Path(db_path).parent/'originals'
        original_dir.mkdir(exist_ok=True)
        original_zip=original_dir/(digest+'.zip')
        if not original_zip.exists():
            original_zip.write_bytes(content)
    return {"feed_id":fid,"sha256":digest,"operator":operator,"min_date":low,"max_date":high,"routes":len(data['routes']),"stops":len(data['stops']),"trips":len(data['trips']),"already_imported":False}

def versions(conn):
    return [dict(x) for x in conn.execute('SELECT * FROM feeds ORDER BY snapshot_date DESC, id DESC')]

def pick_version(conn, operator, day):
    """For historical days, never use a source captured after frozen cutoff.

    Future planning may use a later feed, but is never labelled historical.
    Snapshot-on-date is provenance, not certification of performed service.
    """
    ceiling=CUTOFF.isoformat() if date.fromisoformat(day)<=CUTOFF else date.today().isoformat()
    candidates=conn.execute('SELECT * FROM feeds WHERE operator=? AND min_date<=? AND max_date>=? AND snapshot_date<=? ORDER BY snapshot_date DESC,id DESC',(operator,day,day,ceiling)).fetchall()
    if not candidates: return None, 'missing'
    prior=[r for r in candidates if r['snapshot_date']<=day]
    if prior: return prior[0], 'snapshot_on_or_before_date'
    return sorted(candidates,key=lambda r:r['snapshot_date'])[0], 'retrospective_snapshot'

def active_services(conn,fid,day):
    wd=date.fromisoformat(day).weekday()
    field=['mon','tue','wed','thu','fri','sat','sun'][wd]
    out={r['service_id'] for r in conn.execute(f'SELECT service_id FROM services WHERE feed_id=? AND start_date<=? AND end_date>=? AND {field}=1',(fid,day,day))}
    for r in conn.execute('SELECT service_id,exception_type FROM exceptions WHERE feed_id=? AND service_date=?',(fid,day)):
        if r['exception_type']==1: out.add(r['service_id'])
        elif r['exception_type']==2: out.discard(r['service_id'])
    return out

def day_category(d):
    wd=d.weekday()
    return 'LJ' if wd<4 else 'V' if wd==4 else 'S' if wd==5 else 'D'

def all_days(year,month,day_type):
    return [date(year,month,d) for d in range(1,cal.monthrange(year,month)[1]+1) if day_category(date(year,month,d))==day_type]

def date_trip_rows(conn,feed_id,services,hour_start=0,hour_end=2880):
    if not services: return []
    markers=','.join('?' for _ in services)
    sql=f'''SELECT t.trip_id,t.route_id,t.direction_id,t.headsign,r.short_name,r.long_name,
      (SELECT s.dep_min FROM stop_times s WHERE s.feed_id=t.feed_id AND s.trip_id=t.trip_id ORDER BY s.seq LIMIT 1) AS first_dep,
      (SELECT s.stop_id FROM stop_times s WHERE s.feed_id=t.feed_id AND s.trip_id=t.trip_id ORDER BY s.seq LIMIT 1) AS origin_id
      FROM trips t JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
      WHERE t.feed_id=? AND t.service_id IN ({markers})'''
    out=[]
    for row in conn.execute(sql,(feed_id,*services)):
        if row['first_dep'] is not None and hour_start<=row['first_dep']<hour_end:
            out.append(dict(row))
    return out

def month_analysis(conn, operator,year,month,day_type,hour_start=0,hour_end=2880,route_filter='',calendar_filter='all'):
    if operator not in OPERATORS or day_type not in ('LJ','V','S','D') or calendar_filter not in ('all','ordinary','exception') or not 2025<=year<=2026 or not 1<=month<=12:
        raise ValueError('Filtros no válidos')
    result={"operator":operator,"year":year,"month":month,"day_type":day_type,"hour_start":hour_start,"hour_end":hour_end,"cutoff":CUTOFF.isoformat(),"calendar_filter":calendar_filter,"segments":[]}
    grouped={"historical":[],"planning":[]}
    for d in all_days(year,month,day_type):
        segment='historical' if d<=CUTOFF else 'planning'
        version,confidence=pick_version(conn,operator,d.isoformat())
        if version is None:
            grouped[segment].append({"date":d.isoformat(),"source":"missing","trips":[],"snapshot_quality":"missing"})
            continue
        explicit_exceptions=conn.execute('SELECT COUNT(*) AS n FROM exceptions WHERE feed_id=? AND service_date=?',(version['id'],d.isoformat())).fetchone()['n']
        if calendar_filter=='ordinary' and explicit_exceptions or calendar_filter=='exception' and not explicit_exceptions:
            continue
        sid=active_services(conn,version['id'],d.isoformat())
        trips=date_trip_rows(conn,version['id'],sid,hour_start,hour_end)
        if route_filter: trips=[r for r in trips if r['route_id']==route_filter]
        grouped[segment].append({"date":d.isoformat(),"source":version['id'],"sha256":version['sha256'],"snapshot_quality":confidence,"explicit_exception":bool(explicit_exceptions),"trips":trips})
    for segment,items in grouped.items():
        if not items: continue
        good=[d for d in items if d['source']!='missing']
        total_count=sum(len(d['trips']) for d in good)
        by_line=defaultdict(lambda:{'counts':0,'departures':defaultdict(list),'directions':set(), 'short_name':'','long_name':''})
        for day in good:
            for t in day['trips']:
                b=by_line[t['route_id']]
                b['counts']+=1
                b['short_name']=t['short_name'];b['long_name']=t['long_name']
                b['directions'].add(str(t['direction_id'] or '0'))
                b['departures'][(day['date'],str(t['direction_id'] or '0'),t['headsign'] or '')].append(t['first_dep'])
        lines=[]
        for route_id,detail in by_line.items():
            intervals=[]
            for departures in detail['departures'].values():
                ordered=sorted(departures)
                intervals += [b-a for a,b in zip(ordered,ordered[1:]) if b>=a]
            lines.append({"route_id":route_id,"name":detail['short_name'] or route_id,"long_name":detail['long_name'],
             "trips_per_day":round(detail['counts']/len(good),2) if good else None,
             "median_interval":round(statistics.median(intervals),1) if intervals else None,
             "direction_count":len(detail['directions'])})
        lines.sort(key=lambda x:x['name'])
        result['segments'].append({"state":segment,"from":items[0]['date'],"to":items[-1]['date'],
         "days_total":len(items),"days_available":len(good),"days_missing":len(items)-len(good),
         "days_retrospective":sum(d['snapshot_quality']=='retrospective_snapshot' for d in good),
         "average_trips_per_day":round(total_count/len(good),2) if good else None,
         "total_trips":total_count if good else None, "lines":lines,
         "complete_source_coverage":len(good)==len(items),"certified":False,
         "days_explicit_exception":sum(bool(d.get('explicit_exception')) for d in good),
         "daily": [{"date":d['date'],"trips":len(d['trips']) if d['source']!='missing' else None,"status":d['snapshot_quality'],"exception":bool(d.get('explicit_exception')),"feed_id":d['source']} for d in items]})
    return result

def map_data(conn, operator,day,route_filter=''):
    if operator not in OPERATORS: raise ValueError('Operador no válido')
    day=clean_date(day)
    v,quality=pick_version(conn,operator,day)
    if not v: return {"stops":[],"routes":[],"quality":"missing","day":day}
    fid=v['id']; services=active_services(conn,fid,day)
    if not services: return {"stops":[],"routes":[],"quality":quality,"day":day,'feed_id':fid}
    marks=','.join('?' for _ in services)
    active_routes={r['route_id'] for r in conn.execute(f'SELECT DISTINCT route_id FROM trips WHERE feed_id=? AND service_id IN ({marks})',(fid,*services))}
    if route_filter: active_routes.intersection_update([route_filter])
    lines=[];stop_ids=set()
    for route_id in sorted(active_routes):
        r=conn.execute('SELECT * FROM routes WHERE feed_id=? AND route_id=?',(fid,route_id)).fetchone()
        patterns=conn.execute(f'''SELECT DISTINCT shape_id,direction_id FROM trips
            WHERE feed_id=? AND route_id=? AND service_id IN ({marks}) ORDER BY direction_id,shape_id LIMIT 15''' ,(fid,route_id,*services)).fetchall()
        # Include all served stops across every active trip/variant, not a single pattern.
        all_stop_rows=conn.execute(f'''SELECT DISTINCT st.stop_id FROM stop_times st
          JOIN trips t ON t.feed_id=st.feed_id AND t.trip_id=st.trip_id
          WHERE st.feed_id=? AND t.route_id=? AND t.service_id IN ({marks})''',(fid,route_id,*services))
        stop_ids.update(s['stop_id'] for s in all_stop_rows)
        for pattern in patterns:
            shape_id=pattern['shape_id']
            points=conn.execute('SELECT lat,lon FROM shapes WHERE feed_id=? AND shape_id=? ORDER BY seq',(fid,shape_id)).fetchall()
            coords=[[s['lon'],s['lat']] for s in points if s['lon'] is not None and s['lat'] is not None]
            if not coords:
                t=conn.execute(f'''SELECT trip_id FROM trips WHERE feed_id=? AND route_id=? AND service_id IN ({marks})
                     AND COALESCE(shape_id,'')=COALESCE(?,'') AND COALESCE(direction_id,'')=COALESCE(?,'') LIMIT 1''',(fid,route_id,*services,shape_id,pattern['direction_id'])).fetchone()
                if t:
                    rows=conn.execute('SELECT s.lon,s.lat FROM stop_times st JOIN stops s ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id WHERE st.feed_id=? AND st.trip_id=? ORDER BY st.seq',(fid,t['trip_id'])).fetchall()
                    coords=[[p['lon'],p['lat']] for p in rows if p['lon'] is not None and p['lat'] is not None]
            if coords:
                lines.append({'id':route_id,'name':r['short_name'] or route_id,'long_name':r['long_name'],
                    'direction':pattern['direction_id'],'shape_id':shape_id,
                    'coordinates':coords[::max(1,len(coords)//350)]})
    stops=[]
    if stop_ids:
        marks=','.join('?' for _ in stop_ids)
        stops=[{'id':s['stop_id'],'name':s['name'],'lat':s['lat'],'lon':s['lon']} for s in conn.execute(f'SELECT * FROM stops WHERE feed_id=? AND stop_id IN ({marks})',(fid,*stop_ids)) if s['lon'] is not None and s['lat'] is not None]
    return {'feed_id':fid,'quality':quality,'day':day,'state':'historical' if date.fromisoformat(day)<=CUTOFF else 'planning','routes':lines,'stops':stops,'snapshot_date':v['snapshot_date']}

def stop_departures(conn,operator,day,stop_id):
    day=clean_date(day);v,quality=pick_version(conn,operator,day)
    if not v: return {"departures":[],"status":"missing"}
    sid=active_services(conn,v['id'],day)
    if not sid:return {"departures":[],"status":quality}
    marks=','.join('?' for _ in sid)
    sql=f'''SELECT st.dep_min,r.short_name,t.headsign,t.direction_id FROM stop_times st
       JOIN trips t ON t.feed_id=st.feed_id AND t.trip_id=st.trip_id
       JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
       WHERE st.feed_id=? AND st.stop_id=? AND t.service_id IN ({marks}) ORDER BY st.dep_min'''
    return {"status":quality,"state":"historical" if date.fromisoformat(day)<=CUTOFF else "planning","departures":[{'time':fmt_minutes(x['dep_min']),'line':x['short_name'],'destination':x['headsign'],'direction':x['direction_id']} for x in conn.execute(sql,(v['id'],stop_id,*sid))]}


def historical_comparison(conn,operator,month,day_type,hour_start=0,hour_end=2880):
    """Compare the same calendar window and weekday category, only historical days.

    Comparison is exploratory, never labelled as certified or actually operated.
    It refuses to calculate a delta if either source has any missing date.
    """
    if month<1 or month>12 or operator not in OPERATORS or day_type not in ('LJ','V','S','D'):
        raise ValueError('Filtros inválidos')
    # In October only 1-18 is historical in 2026. In Nov/Dec there are none.
    days2026=[d for d in all_days(2026,month,day_type) if d<=CUTOFF]
    if not days2026:
        return {'operator':operator,'month':month,'day_type':day_type,'comparable':False,
                'reason':'No hay histórico de 2026 para este periodo; solo planificación',
                'cutoff':CUTOFF.isoformat(),'2025':None,'2026':None,'delta_pct':None}
    last_day=max(d.day for d in days2026)
    # Restrict both years to same day-of-month range; weekday distributions
    # differ so daily mean (not total monthly service) is the comparison unit.
    out={}
    for year in (2025,2026):
        days=[d for d in all_days(year,month,day_type) if d.day<=last_day]
        values=[];retrospective=0;missing=[];sources=set()
        for d in days:
            v,quality=pick_version(conn,operator,d.isoformat())
            if not v:
                missing.append(d.isoformat());continue
            services=active_services(conn,v['id'],d.isoformat())
            rows=date_trip_rows(conn,v['id'],services,hour_start,hour_end)
            values.append(len(rows));sources.add(v['sha256'])
            if quality=='retrospective_snapshot':retrospective+=1
        out[str(year)]={'days_expected':len(days),'days_available':len(values),
         'days_missing':missing,'retrospective_days':retrospective,
         'average_trips_per_day':round(sum(values)/len(values),2) if values else None,
         'source_hashes':sorted(sources)}
    valid=bool(out['2025']['days_expected'] and out['2026']['days_expected']
          and not out['2025']['days_missing'] and not out['2026']['days_missing'])
    a=out['2025']['average_trips_per_day'];b=out['2026']['average_trips_per_day']
    delta=round((b-a)/a*100,2) if valid and a is not None and a>0 and b is not None else None
    return {'operator':operator,'month':month,'day_type':day_type,'cutoff':CUTOFF.isoformat(),
            'period_window':f'1-{last_day} de cada mes','comparable':valid,'certified':False,
            'reason':'Cálculo exploratorio; falta certificación de versiones históricas' if valid else 'Faltan fechas con fuente validable en uno o ambos periodos',
            '2025':out['2025'],'2026':out['2026'],'delta_pct':delta}
