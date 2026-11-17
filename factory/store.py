"""Single SQLite queue with atomic claims, fencing and persisted results."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from . import config


@contextmanager
def connect():
    config.initialize()
    with sqlite3.connect(config.DB, timeout=15) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, state TEXT NOT NULL, request TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT '{}', error TEXT,
            worker TEXT, lease TEXT, seen REAL, created REAL NOT NULL,
            stage TEXT, current REAL, total REAL, cancelled INTEGER DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS workers (
            id TEXT PRIMARY KEY, seen REAL NOT NULL, resources TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY, alias TEXT NOT NULL, title TEXT NOT NULL,
            daily_limit INTEGER NOT NULL DEFAULT 3, public_allowed INTEGER NOT NULL DEFAULT 0,
            automatic INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS publications (
            id TEXT PRIMARY KEY, job TEXT NOT NULL, output INTEGER NOT NULL, channel TEXT NOT NULL,
            state TEXT NOT NULL, metadata TEXT NOT NULL, session TEXT, video_id TEXT,
            current INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
            error TEXT, created REAL NOT NULL, seen REAL, attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(job,output,channel))''')
        db.execute('''CREATE TABLE IF NOT EXISTS channel_schedules (
            channel TEXT PRIMARY KEY, interval_minutes INTEGER NOT NULL DEFAULT 120)''')
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            job TEXT NOT NULL, at REAL NOT NULL, state TEXT NOT NULL, message TEXT)''')
        yield db


def decode(row):
    if row is None:
        return None
    item = dict(row)
    for k in ('request', 'result'):
        item[k] = json.loads(item[k])
    item.pop('lease', None)
    return item


def create(request):
    jid = uuid.uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO jobs(id,state,request,created) VALUES(?,?,?,?)',
                   (jid, 'QUEUED', json.dumps(request, ensure_ascii=False), time.time()))
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),'QUEUED','Job queued'))
    return get(jid)


def get(jid):
    with connect() as db:
        return decode(db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())


def list_jobs():
    with connect() as db:
        return [decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')]


def claim(worker, remote=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # Uncertain external effects must be reviewed, never replayed blindly.
        expired=db.execute("UPDATE jobs SET state='BLOCKED',error='Worker lease expired; inspect outputs before retry',lease=NULL WHERE lease IS NOT NULL AND seen < ? RETURNING id", (time.time()-120,)).fetchall()
        for item in expired:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(item['id'],time.time(),'BLOCKED','Worker lease expired; inspect outputs before retry'))
        if db.execute('SELECT 1 FROM jobs WHERE worker=? AND lease IS NOT NULL',(worker,)).fetchone():
            return None
        rows = db.execute("SELECT id,request FROM jobs WHERE state='QUEUED' AND cancelled=0 ORDER BY created").fetchall()
        row = next((r for r in rows if not remote or (not json.loads(r['request'])['source'].startswith('upload:') and json.loads(r['request'])['save_drive'])),None)
        if not row:
            return None
        lease = uuid.uuid4().hex
        db.execute("UPDATE jobs SET state='PROBING',worker=?,lease=?,seen=? WHERE id=?", (worker,lease,time.time(),row['id']))
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(row['id'],time.time(),'PROBING','Lease assigned to '+worker))
        return {'job': decode(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone()), 'lease': lease}


def update(jid, lease, state=None, result=None, error=None, current=None, total=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM jobs WHERE id=? AND lease=?', (jid,lease)).fetchone()
        if not row or row['cancelled']:
            raise InterruptedError('Job cancelled or worker lease lost')
        value = json.loads(row['result'])
        if result:
            value.update(result)
        if state is None:
            if current is None:
                current=row['current']
            if total is None:
                total=row['total']
        terminal = state in ('READY','FAILED','BLOCKED','CANCELLED')
        db.execute('UPDATE jobs SET state=?,result=?,error=?,current=?,total=?,seen=?,lease=? WHERE id=?',
                   (state or row['state'], json.dumps(value, ensure_ascii=False), error,current,total,time.time(),None if terminal else lease,jid))
        db.execute('UPDATE workers SET seen=? WHERE id=?',(time.time(),row['worker']))
        if state and (state!=row['state'] or error):
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),state,error))


def heartbeat(worker, resources):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO workers VALUES(?,?,?)', (worker,time.time(),json.dumps(resources)))


def workers():
    with connect() as db:
        return [{**dict(r),'resources':json.loads(r['resources'])} for r in db.execute('SELECT * FROM workers')]


def events(jid):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT at,state,message FROM events WHERE job=? ORDER BY at DESC LIMIT 100',(jid,))]


def cancel(jid):
    with connect() as db:
        cur=db.execute("UPDATE jobs SET cancelled=1,state='CANCELLED',lease=NULL WHERE id=? AND state NOT IN ('READY','PUBLISHED')", (jid,))
        if cur.rowcount:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),'CANCELLED','Cancelled by operator'))


def retry(jid):
    with connect() as db:
        # A retry resumes files/checkpoints; verified Drive outputs are retained.
        cur = db.execute("UPDATE jobs SET state='QUEUED',error=NULL,cancelled=0,lease=NULL WHERE id=? AND state IN ('FAILED','BLOCKED','CANCELLED')", (jid,))
        if cur.rowcount:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),'QUEUED','Manual retry; checkpoints retained'))
        return cur.rowcount == 1


def approve(jid,index,value):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT state,result FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row or row['state']!='READY':
            raise ValueError('Only a completed output can be approved')
        result=json.loads(row['result'])
        result['outputs'][index]['approved']=value
        db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),jid))
