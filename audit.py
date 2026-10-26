"""Evidence-led release audit for the frozen 2025-01-01..2026-10-18 baseline.

A feed with a valid service calendar is never itself a certified timetable.
Source selection, day-level reviews and the release gate are separate layers.
"""
from __future__ import annotations
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from typing import Iterable
import engine
import data_quality

START = date(2025, 1, 1)
END = engine.CUTOFF
MONTHS = tuple((year, month) for year in (2025, 2026) for month in range(1, 13))
REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS service_reviews (
 id INTEGER PRIMARY KEY,
 operator TEXT NOT NULL,
 service_date TEXT NOT NULL,
 feed_id INT NOT NULL,
 sha256 TEXT NOT NULL,
 review_state TEXT NOT NULL CHECK(review_state IN ('verified','rejected')),
 reviewer TEXT NOT NULL,
 evidence TEXT NOT NULL,
 reviewed_at TEXT NOT NULL,
 UNIQUE(operator,service_date)
);
CREATE INDEX IF NOT EXISTS ix_service_reviews_date ON service_reviews(operator,service_date);
"""


def setup(conn:sqlite3.Connection):
    conn.executescript(REVIEW_SCHEMA)


def require_review_schema(conn:sqlite3.Connection):
    """Fail explicitly if startup migrations were skipped; never mutate on GET."""
    present=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='service_reviews'").fetchone()
    if not present:raise RuntimeError('La base no está migrada: falta service_reviews')


def each_day(start:date, end:date):
    current=start
    while current<=end:
        yield current
        current += timedelta(days=1)


def provenance_day(conn, operator:str, d:date):
    source,quality=engine.pick_version(conn,operator,d.isoformat())
    review=conn.execute('SELECT * FROM service_reviews WHERE operator=? AND service_date=?', (operator,d.isoformat())).fetchone()
    compatible=bool(source and review and review['feed_id']==source['id'] and review['sha256']==source['sha256'])
    if d>END:
        state='planning' if source else 'planning_missing'
    elif not source:
        state='missing'
    elif compatible and review['review_state']=='verified':
        state='verified'
    elif compatible and review['review_state']=='rejected':
        state='rejected'
    else:
        state='located_unverified'
    return {'date':d.isoformat(), 'state':state,
        'data_type':'planning' if d>END else 'historical_programmed',
        'feed_id':source['id'] if source else None,
        'source_quality':quality,
        'snapshot_date':source['snapshot_date'] if source else None,
        'evidence':review['evidence'] if compatible else None}


def month_grid(conn, operator:str, year:int):
    if operator not in engine.OPERATORS or year not in (2025,2026):
        raise ValueError('Operador o año no válido')
    require_review_schema(conn)
    out=[]
    for month in range(1,13):
        dates=[provenance_day(conn,operator,d) for d in each_day(date(year,month,1),date(year,month,monthrange(year,month)[1]))]
        counts=Counter(x['state'] for x in dates)
        out.append({'year':year,'month':month,'days':len(dates),
             'historical_days':sum(1 for x in dates if x['data_type']=='historical_programmed'),
             'planning_days':sum(1 for x in dates if x['data_type']=='planning'),
             'states':dict(counts),
             'ready':bool(any(x['data_type']=='historical_programmed' for x in dates)) and all(x['state']=='verified' for x in dates if x['data_type']=='historical_programmed'),
             'dates':dates})
    return {'operator':operator,'year':year,'cutoff':END.isoformat(),'months':out}


def review_period(conn, operator:str, from_day:str, to_day:str,
                  reviewer:str,evidence:str,status:str='verified'):
    setup(conn)
    if operator not in engine.OPERATORS or status not in ('verified','rejected'):
        raise ValueError('Operador o estado incorrecto')
    reviewer=reviewer.strip();evidence=evidence.strip()
    if len(reviewer)<3 or len(evidence)<15:
        raise ValueError('Requiere revisor identificado y evidencia documentada (15 caracteres o más)')
    start=date.fromisoformat(engine.clean_date(from_day));end=date.fromisoformat(engine.clean_date(to_day))
    if start<START or end>END or start>end or (end-start).days>93:
        raise ValueError('Rango fuera del histórico 2025–18/10/2026 o superior a 94 días')
    rows=[]
    for d in each_day(start,end):
        version,quality=engine.pick_version(conn,operator,d.isoformat())
        if version is None:
            raise ValueError('No se puede verificar un día sin fuente: '+d.isoformat())
        rows.append((operator,d.isoformat(),version['id'],version['sha256'],status,reviewer,evidence,
            datetime.now(timezone.utc).isoformat(timespec='seconds')))
    with conn:
        conn.executemany('''INSERT INTO service_reviews(operator,service_date,feed_id,sha256,review_state,reviewer,evidence,reviewed_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(operator,service_date) DO UPDATE SET
            feed_id=excluded.feed_id,sha256=excluded.sha256,review_state=excluded.review_state,
            reviewer=excluded.reviewer,evidence=excluded.evidence,reviewed_at=excluded.reviewed_at''',rows)
    return {'reviewed':len(rows),'status':status,'operator':operator,'from':start.isoformat(),'to':end.isoformat(),
        'note':'La revisión documental acredita la fuente y el horario programado, no que las expediciones se prestaran.'}


def readiness(conn, geographic_status=None):
    require_review_schema(conn)
    breakdown={};missing_examples=[];not_verified_examples=[]
    expected_days=(END-START).days+1
    # The frozen publication gate covers the historical bus baseline.  The
    # current Euskotren/Errenteria additions are selectable real data, but
    # they do not retroactively create a 2025–18/10/2026 audit obligation.
    for operator in engine.CORE_OPERATORS:
        counter=Counter()
        for d in each_day(START,END):
            rec=provenance_day(conn,operator,d)
            counter[rec['state']]+=1
            if rec['state']=='missing' and len(missing_examples)<16:missing_examples.append({'operator':operator,'date':rec['date']})
            if rec['state'] in ('located_unverified','rejected') and len(not_verified_examples)<16:
                not_verified_examples.append({'operator':operator,'date':rec['date'],'state':rec['state']})
        breakdown[operator]={'expected_historical_days':expected_days,'verified':counter['verified'],
            'located_unverified':counter['located_unverified'],'missing':counter['missing'],
            'rejected':counter['rejected']}
    geo=geographic_status or {}
    # The geographic gate cannot pass merely because the files exist; all six
    # municipalities and a pedestrian network must be represented.
    geo_munis=set(geo.get('municipalities',[]))
    geo_ready=(set(('Irun','Hondarribia','Errenteria','Pasaia','Lezo','Oiartzun'))<=geo_munis
               and geo.get('resident_units',0)>0 and geo.get('walk_segments',0)>0
               and geo.get('unallocated_population',float('inf'))==0)
    hist_ready=all(v['verified']==expected_days for v in breakdown.values())
    used_feed_ids={r['feed_id'] for r in conn.execute("SELECT DISTINCT feed_id FROM service_reviews WHERE review_state='verified'")}
    quality_results=[data_quality.validate_feed(conn,fid) for fid in used_feed_ids]
    structural_ready=bool(used_feed_ids) and all(r['structurally_valid'] for r in quality_results)
    reasons=[]
    if not hist_ready:reasons.append('Histórico diario sin certificación completa para ambos operadores')
    if not geo_ready:reasons.append('Modelo residencial o red peatonal sin certificación de cobertura de seis municipios')
    if not structural_ready:reasons.append('Hay feeds utilizados sin validación estructural o no hay feeds verificados')
    return {'publication_ready':False, 'data_gate_passed':hist_ready and geo_ready and structural_ready,
        'historical_cutoff':END.isoformat(),'historical_start':START.isoformat(),
        'target_days_per_operator':expected_days,'operators':breakdown,
        'geographic_gate_passed':geo_ready,'structural_gate_passed':structural_ready,
        'structural_issues':[r for r in quality_results if not r['structurally_valid']],
        'unresolved_examples':missing_examples,
        'review_pending_examples':not_verified_examples,
        'reasons':reasons+['La publicación requiere además revisión de seguridad, accesibilidad, despliegue y aprobación humana.'],
        'note':'Este verificador nunca publica automáticamente la aplicación.'}
