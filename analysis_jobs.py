"""Durable bounded queue for expensive analyses.

The API only enqueues and reads state. ``worker.py`` owns calculations, so a
large network union cannot block the process serving maps and timetables.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA="""
CREATE TABLE IF NOT EXISTS analysis_jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, params_json TEXT NOT NULL,
 cache_key TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
 result_json TEXT, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_status_created ON analysis_jobs(status,created_at);
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_cache ON analysis_jobs(cache_key,status);
"""


def utcnow():return datetime.now(timezone.utc).isoformat()


def connect(path):
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(target,timeout=30,isolation_level=None);conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL');conn.execute('PRAGMA busy_timeout=30000');conn.executescript(SCHEMA)
    return conn


def make_cache_key(kind,params,release_id,method_version):
    raw=json.dumps({'kind':kind,'params':params,'release':release_id,'method':method_version},sort_keys=True,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue(path,kind,params,release_id,method_version,max_pending=50):
    key=make_cache_key(kind,params,release_id,method_version)
    conn=connect(path)
    try:
        existing=conn.execute("SELECT * FROM analysis_jobs WHERE cache_key=? AND status IN ('complete','pending','running') ORDER BY created_at DESC LIMIT 1",(key,)).fetchone()
        if existing:return public(existing,reused=True)
        pending=int(conn.execute("SELECT COUNT(*) FROM analysis_jobs WHERE status IN ('pending','running')").fetchone()[0])
        if pending>=max_pending:raise OverflowError('La cola de análisis está completa')
        ident=str(uuid.uuid4())
        conn.execute("INSERT INTO analysis_jobs(id,kind,params_json,cache_key,status,created_at) VALUES (?,?,?,?,?,?)",
                     (ident,kind,json.dumps(params,separators=(',',':')) ,key,'pending',utcnow()))
        return public(conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone())
    finally:conn.close()


def get(path,ident):
    conn=connect(path)
    try:return public(conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone())
    finally:conn.close()


def cancel(path,ident):
    conn=connect(path)
    try:
        conn.execute("UPDATE analysis_jobs SET cancel_requested=1,status=CASE WHEN status='pending' THEN 'cancelled' ELSE status END,completed_at=CASE WHEN status='pending' THEN ? ELSE completed_at END WHERE id=? AND status IN ('pending','running')",(utcnow(),ident))
        return public(conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(ident,)).fetchone())
    finally:conn.close()


def claim(path,timeout_seconds):
    conn=connect(path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        threshold=(datetime.now(timezone.utc)-timedelta(seconds=timeout_seconds)).isoformat()
        conn.execute("UPDATE analysis_jobs SET status='failed',completed_at=?,error='Tiempo máximo superado' WHERE status='running' AND started_at<?",(utcnow(),threshold))
        row=conn.execute("SELECT * FROM analysis_jobs WHERE status='pending' AND cancel_requested=0 ORDER BY created_at LIMIT 1").fetchone()
        if row:
            conn.execute("UPDATE analysis_jobs SET status='running',started_at=? WHERE id=? AND status='pending'",(utcnow(),row['id']))
            row=conn.execute('SELECT * FROM analysis_jobs WHERE id=?',(row['id'],)).fetchone()
        conn.execute('COMMIT');return row
    except Exception:
        conn.execute('ROLLBACK');raise
    finally:conn.close()


def finish(path,ident,result=None,error=None):
    conn=connect(path)
    try:
        cancelled=conn.execute('SELECT cancel_requested FROM analysis_jobs WHERE id=?',(ident,)).fetchone()
        if cancelled and cancelled[0]:status='cancelled';result=None;error='Cancelado por el usuario'
        else:status='failed' if error else 'complete'
        conn.execute("UPDATE analysis_jobs SET status=?,completed_at=?,result_json=?,error=? WHERE id=?",
                     (status,utcnow(),json.dumps(result,separators=(',',':')) if result is not None else None,(error or '')[:2000],ident))
    finally:conn.close()


def public(row,reused=False):
    if row is None:return None
    result=json.loads(row['result_json']) if row['result_json'] else None
    return {'id':row['id'],'kind':row['kind'],'status':row['status'],'created_at':row['created_at'],
            'started_at':row['started_at'],'completed_at':row['completed_at'],'result':result,
            'error':row['error'] or None,'reused':reused}
