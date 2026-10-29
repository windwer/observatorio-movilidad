"""Atomic durable jobs with expiring execution leases and worker heartbeats."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import uuid
import threading
from datetime import datetime,timedelta,timezone
from pathlib import Path

_INIT_LOCK=threading.Lock()
_INITIALIZED=set()
SCHEMA="""
CREATE TABLE IF NOT EXISTS analysis_jobs(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,params_json TEXT NOT NULL,
 cache_key TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
 started_at TEXT,completed_at TEXT,result_json TEXT,error TEXT,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT,lease_expires_at TEXT,worker_id TEXT,attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_status_created ON analysis_jobs(status,created_at);
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_cache ON analysis_jobs(cache_key,status);
CREATE TABLE IF NOT EXISTS worker_heartbeats(
 worker_id TEXT PRIMARY KEY,heartbeat_at TEXT NOT NULL,data_identity TEXT NOT NULL,status TEXT NOT NULL);
"""

def utcnow():return datetime.now(timezone.utc).isoformat()

def connect(path):
    target=Path(path).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    existed=target.exists()
    conn=sqlite3.connect(target,timeout=30,isolation_level=None);conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    with _INIT_LOCK:
        if not existed or str(target) not in _INITIALIZED:
            conn.execute('PRAGMA journal_mode=WAL');conn.executescript(SCHEMA)
            conn.execute('BEGIN IMMEDIATE')
            try:
                columns={row['name'] for row in conn.execute('PRAGMA table_info(analysis_jobs)')}
                for name,definition in [('lease_token','TEXT'),('lease_expires_at','TEXT'),('worker_id','TEXT'),('attempts','INTEGER NOT NULL DEFAULT 0')]:
                    if name not in columns:conn.execute(f'ALTER TABLE analysis_jobs ADD COLUMN {name} {definition}')
                conn.execute("""UPDATE analysis_jobs SET status='failed',error='Duplicate legacy job'
                    WHERE status IN ('pending','running') AND rowid NOT IN
                    (SELECT MIN(rowid) FROM analysis_jobs WHERE status IN ('pending','running') GROUP BY cache_key)""")
                conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_active_job
                    ON analysis_jobs(cache_key) WHERE status IN ('pending','running')""")
                conn.execute('COMMIT');_INITIALIZED.add(str(target))
            except Exception:
                conn.execute('ROLLBACK');conn.close();raise
    return conn

def make_cache_key(kind,params,release_id,method_version):
    raw=json.dumps({'kind':kind,'params':params,'release':release_id,'method':method_version},sort_keys=True,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()

def enqueue(path,kind,params,release_id,method_version,max_pending=50):
    key=make_cache_key(kind,params,release_id,method_version);conn=connect(path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        existing=conn.execute("SELECT * FROM analysis_jobs WHERE cache_key=? AND status IN ('complete','pending','running') ORDER BY created_at DESC LIMIT 1",(key,)).fetchone()
        if existing:
            conn.execute('COMMIT');return public(existing,reused=True)
        pending=conn.execute("SELECT COUNT(*) FROM analysis_jobs WHERE status IN ('pending','running')").fetchone()[0]
        if pending>=max_pending:raise OverflowError('La cola de análisis está completa')
        ident=str(uuid.uuid4())
        conn.execute("INSERT INTO analysis_jobs(id,kind,params_json,cache_key,status,created_at) VALUES (?,?,?,?,?,?)",
                     (ident,kind,json.dumps(params,separators=(',',':')),key,'pending',utcnow()))
        row=conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone()
        conn.execute('COMMIT');return public(row)
    except Exception:
        if conn.in_transaction:conn.execute('ROLLBACK')
        raise
    finally:conn.close()

def get(path,ident):
    conn=connect(path)
    try:return public(conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone())
    finally:conn.close()

def cancel(path,ident):
    conn=connect(path)
    try:
        conn.execute("""UPDATE analysis_jobs SET cancel_requested=1,status='cancelled',completed_at=?,
            lease_token=NULL,lease_expires_at=NULL WHERE id=? AND status IN ('pending','running')""",(utcnow(),ident))
        return public(conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone())
    finally:conn.close()

def claim(path,timeout_seconds,worker_id='local-worker'):
    conn=connect(path)
    try:
        conn.execute('BEGIN IMMEDIATE');now=utcnow()
        conn.execute("""UPDATE analysis_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END,
            error='Worker lease expired',lease_token=NULL,lease_expires_at=NULL
            WHERE status='running' AND (lease_expires_at IS NULL OR lease_expires_at<?)""",(now,))
        row=conn.execute("SELECT * FROM analysis_jobs WHERE status='pending' AND cancel_requested=0 ORDER BY created_at LIMIT 1").fetchone()
        if row:
            token=str(uuid.uuid4());expires=(datetime.now(timezone.utc)+timedelta(seconds=min(30,timeout_seconds))).isoformat()
            conn.execute("""UPDATE analysis_jobs SET status='running',started_at=?,worker_id=?,
                lease_token=?,lease_expires_at=?,attempts=attempts+1 WHERE id=? AND status='pending'""",
                (now,worker_id,token,expires,row['id']))
            row=conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(row['id'],)).fetchone()
        conn.execute('COMMIT');return row
    except Exception:
        if conn.in_transaction:conn.execute('ROLLBACK')
        raise
    finally:conn.close()

def renew(path,ident,token,seconds=30):
    conn=connect(path)
    try:
        now=utcnow();expires=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
        return conn.execute("""UPDATE analysis_jobs SET lease_expires_at=? WHERE id=? AND lease_token=?
            AND status='running' AND cancel_requested=0 AND lease_expires_at>=?""",(expires,ident,token,now)).rowcount==1
    finally:conn.close()

def finish(path,ident,result=None,error=None,*,lease_token):
    conn=connect(path)
    try:
        return conn.execute("""UPDATE analysis_jobs SET status=?,completed_at=?,result_json=?,error=?,
            lease_token=NULL,lease_expires_at=NULL WHERE id=? AND status='running'
            AND lease_token=? AND lease_expires_at>=? AND cancel_requested=0""",
            ('failed' if error else 'complete',utcnow(),json.dumps(result,separators=(',',':')) if result is not None else None,
             (error or '')[:2000],ident,lease_token,utcnow())).rowcount==1
    finally:conn.close()

def heartbeat(path,worker_id,data_identity,status='ready'):
    conn=connect(path)
    try:conn.execute('INSERT OR REPLACE INTO worker_heartbeats VALUES (?,?,?,?)',(worker_id,utcnow(),data_identity,status))
    finally:conn.close()

def worker_status(path,data_identity,max_age=15):
    conn=connect(path)
    try:
        threshold=(datetime.now(timezone.utc)-timedelta(seconds=max_age)).isoformat()
        alive=conn.execute('SELECT COUNT(*) FROM worker_heartbeats WHERE heartbeat_at>=? AND data_identity=?',(threshold,data_identity)).fetchone()[0]
        counts={row['status']:row['n'] for row in conn.execute('SELECT status,COUNT(*) n FROM analysis_jobs GROUP BY status')}
        return {'healthy':bool(alive),'workers':alive,'jobs':counts}
    finally:conn.close()

def prune(path,days=30):
    conn=connect(path)
    try:
        threshold=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        jobs=conn.execute("DELETE FROM analysis_jobs WHERE status IN ('complete','failed','cancelled') AND COALESCE(completed_at,created_at)<?",(threshold,)).rowcount
        conn.execute('DELETE FROM worker_heartbeats WHERE heartbeat_at<?',(threshold,))
        return {'deleted_jobs':jobs}
    finally:conn.close()

def public(row,reused=False):
    if row is None:return None
    return {'id':row['id'],'kind':row['kind'],'status':row['status'],'created_at':row['created_at'],
            'started_at':row['started_at'],'completed_at':row['completed_at'],
            'result':json.loads(row['result_json']) if row['result_json'] else None,
            'error':row['error'] or None,'reused':reused}
