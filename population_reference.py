"""Import and verify the provided official Eustat Gipuzkoa 2025 section table.

Counts are reference population per census SECTION only, not spatial stop coverage.
Original CSV is retained unchanged with SHA256. No map geometry is inferred.
"""
from __future__ import annotations
import hashlib
import sqlite3
from collections import defaultdict
from pathlib import Path
from normalize_eustat import parse, read_rows

REFERENCE='2025-01-01'
SOURCE_URL='https://es.eustat.eus/elementos/xls0011434_c.csv'
REGIONS={'Bidasoaldea':('Irun','Hondarribia'), 'Oarsoaldea':('Errenteria','Pasaia','Lezo','Oiartzun')}


def number(x):
    x=str(x).strip().replace('\xa0','').replace(' ','')
    if not x or ',' in x:return None
    x=x.replace('.','')
    return int(x) if x.isdigit() else None


def verify_district_subtotals(raw, sections):
    """Census districts have `Secc=000` rows; sum of children MUST match."""
    current_code=None; district=None; expected={}
    codes={s['municipality_code'] for s in sections}
    for row in read_rows(raw):
        if len(row)<5:continue
        code,name,dist,section,total=(str(x).strip() for x in row[:5])
        if code.isdigit():
            current_code=code.zfill(3) if code.zfill(3) in codes else None
            district=None
        if current_code is None:continue
        if dist.isdigit():district=dist.zfill(2)
        if district and section.isdigit() and int(section)==0:
            value=number(total)
            if value is None:raise ValueError('Subtotal de distrito sin población válida')
            key=(current_code,district)
            if key in expected:raise ValueError('Subtotal de distrito duplicado: '+str(key))
            expected[key]=value
    actual=defaultdict(int)
    for section in sections:
        actual[(section['municipality_code'],section['district'])]+=section['population']
    if set(actual)!=set(expected):
        raise ValueError('No coinciden distritos de secciones y subtotales: '+str(sorted(set(actual)^set(expected))))
    mismatch=[(key,expected[key],actual[key]) for key in actual if expected[key]!=actual[key]]
    if mismatch:raise ValueError('Secciones no cuadran con subtotales Eustat: '+str(mismatch[:6]))
    return len(expected)


def _schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS population_reference_meta(
       reference_date TEXT PRIMARY KEY, source_url TEXT NOT NULL,
       source_name TEXT NOT NULL, sha256 TEXT NOT NULL,
       sections INTEGER NOT NULL, districts INTEGER NOT NULL, total INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS population_sections(
       reference_date TEXT NOT NULL, municipality_code TEXT NOT NULL,
       municipality TEXT NOT NULL, district TEXT NOT NULL, section TEXT NOT NULL,
       population INTEGER NOT NULL CHECK(population>=0),
       PRIMARY KEY(reference_date,municipality_code,district,section));
    CREATE INDEX IF NOT EXISTS idx_pop_municipality ON population_sections(municipality);
    ''')


def ingest(db_path, raw:bytes, source_name='eustat_2025_original.csv'):
    if len(raw)>2_000_000:raise ValueError('Archivo excesivamente grande')
    parsed=parse(raw,require_six=True)
    sections=parsed['rows']
    districts=verify_district_subtotals(raw,sections)
    sha=hashlib.sha256(raw).hexdigest()
    total=sum(r['population'] for r in sections)
    path=Path(db_path);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as conn:
        _schema(conn)
        # An invalid new CSV never clears the prior validated data.
        with conn:
            conn.execute('DELETE FROM population_sections WHERE reference_date=?',(REFERENCE,))
            conn.executemany('''INSERT INTO population_sections
                (reference_date,municipality_code,municipality,district,section,population)
                VALUES(?,?,?,?,?,?)''',[(REFERENCE,r['municipality_code'],r['municipality'],r['district'],r['section'],r['population']) for r in sections])
            conn.execute('''INSERT OR REPLACE INTO population_reference_meta
                 (reference_date,source_url,source_name,sha256,sections,districts,total)
                 VALUES (?,?,?,?,?,?,?)''',(REFERENCE,SOURCE_URL,source_name,sha,len(sections),districts,total))
    return summary(db_path)


def load_if_needed(db_path,source_path):
    source=Path(source_path)
    if source.exists():
        raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        with sqlite3.connect(db_path) as conn:
            _schema(conn)
            meta=conn.execute('SELECT sha256 FROM population_reference_meta WHERE reference_date=?',(REFERENCE,)).fetchone()
        if not meta or meta[0]!=digest:
            return ingest(db_path,raw,source_name=source.name)
    return summary(db_path)


def summary(db_path):
    path=Path(db_path)
    if not path.exists():return {'loaded':False,'reference_date':REFERENCE,'source_url':SOURCE_URL,'geometry_joined':False}
    with sqlite3.connect(path) as conn:
        _schema(conn)
        m=conn.execute('''SELECT source_name,sha256,sections,districts,total FROM population_reference_meta
                          WHERE reference_date=?''',(REFERENCE,)).fetchone()
        if not m:return {'loaded':False,'reference_date':REFERENCE,'source_url':SOURCE_URL,'geometry_joined':False}
        rows=conn.execute('''SELECT municipality,COUNT(*),SUM(population) FROM population_sections
                             WHERE reference_date=? GROUP BY municipality''',(REFERENCE,)).fetchall()
    towns={name:{'sections':count,'population':population} for name,count,population in rows}
    return {'loaded':True,'reference_date':REFERENCE,'source_url':SOURCE_URL,
        'source_name':m[0],'sha256':m[1],'sections':m[2],'districts':m[3],
        'total_population':m[4],'municipalities':towns,
        'by_region':{region:sum(towns[town]['population'] for town in names) for region,names in REGIONS.items()},
        'geometry_joined':False,'spatial_coverage_ready':False,
        'note':'Población censal oficial. NO expresa habitantes dentro de isócronas; falta cartografía de secciones y reparto residencial.'}


def sections(db_path,municipality=''):
    if municipality and municipality not in sum((list(v) for v in REGIONS.values()),[]):
        raise ValueError('Municipio fuera del ámbito de estudio')
    with sqlite3.connect(db_path) as conn:
        _schema(conn)
        if municipality:
            data=conn.execute('''SELECT municipality_code,municipality,district,section,population FROM population_sections
                 WHERE reference_date=? AND municipality=? ORDER BY municipality_code,district,section''',(REFERENCE,municipality)).fetchall()
        else:
            data=conn.execute('''SELECT municipality_code,municipality,district,section,population FROM population_sections
                 WHERE reference_date=? ORDER BY municipality_code,district,section''',(REFERENCE,)).fetchall()
    return {'reference_date':REFERENCE,'municipality':municipality or None,'count':len(data),
            'sections':[{'municipality_code':code,'municipality':town,'district':dist,
                         'section':sect,'population':pop} for code,town,dist,sect,pop in data],
            'geometry_joined':False}
