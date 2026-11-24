"""Single SQLite queue with atomic claims, fencing and persisted results."""
import json
import sqlite3
import time
import uuid
from collections import defaultdict
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
        db.execute('''CREATE TABLE IF NOT EXISTS job_stages (
            job TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL,
            started REAL, finished REAL, current REAL, total REAL, unit TEXT,
            message TEXT, PRIMARY KEY(job,key))''')
        db.execute('''CREATE TABLE IF NOT EXISTS job_operations (
            job TEXT NOT NULL, source_id TEXT NOT NULL, stage_id TEXT NOT NULL,
            operation_id TEXT NOT NULL, lease TEXT NOT NULL, attempt INTEGER NOT NULL,
            status TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL,
            updated_at REAL NOT NULL, processed_units REAL, total_units REAL, unit_type TEXT,
            message TEXT, error_code TEXT, details TEXT NOT NULL,
            PRIMARY KEY(job,source_id,stage_id,operation_id,lease))''')
        db.execute('''CREATE TABLE IF NOT EXISTS metadata_versions (
            job TEXT NOT NULL, output INTEGER NOT NULL, version TEXT NOT NULL,
            metadata TEXT NOT NULL, provenance TEXT NOT NULL, created REAL NOT NULL,
            manual INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(job,output,version))''')
        db.execute('''CREATE TABLE IF NOT EXISTS channel_preferences (
            channel TEXT PRIMARY KEY, preferences TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS analytics_connections (
            channel TEXT PRIMARY KEY, alias TEXT NOT NULL, title TEXT NOT NULL,
            last_sync REAL, last_attempt REAL, state TEXT NOT NULL DEFAULT 'CONNECTED',
            error TEXT, progress INTEGER NOT NULL DEFAULT 0, total INTEGER)''')
        db.execute('''CREATE TABLE IF NOT EXISTS analytics_videos (
            channel TEXT NOT NULL, video TEXT NOT NULL, data TEXT NOT NULL,
            seen REAL NOT NULL, PRIMARY KEY(channel,video))''')
        db.execute('''CREATE TABLE IF NOT EXISTS analytics_reports (
            channel TEXT PRIMARY KEY, report TEXT NOT NULL, seen REAL NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS publication_artifacts (
            publication TEXT PRIMARY KEY, state TEXT NOT NULL, error TEXT, seen REAL NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS media_assets (
            hash TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, metadata TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS retention_packages (
            job TEXT PRIMARY KEY, files TEXT NOT NULL, created REAL NOT NULL,
            protected INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'ACTIVE', error TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS retention_history (
            job TEXT NOT NULL, at REAL NOT NULL, state TEXT NOT NULL, detail TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS factory_settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
        yield db


def decode(row,db=None):
    if row is None:
        return None
    item = dict(row)
    for k in ('request', 'result'):
        item[k] = json.loads(item[k])
    item.pop('lease', None)
    if db is not None:
        item['stages']=[dict(r) for r in db.execute('SELECT key,status,started,finished,current,total,unit,message FROM job_stages WHERE job=? ORDER BY started',(item['id'],))]
    return item


def create(request):
    jid = uuid.uuid4().hex
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if request.get('source','').startswith('edit:'):
            origin=request['source'].split(':')[1]
            package=db.execute('SELECT state FROM retention_packages WHERE job=?',(origin,)).fetchone()
            if package and package['state'] in ('DELETION_PENDING','DELETED'):raise ValueError('Source package is being removed or has expired; restore it before editing')
        db.execute('INSERT INTO jobs(id,state,request,created) VALUES(?,?,?,?)',
                   (jid, 'QUEUED', json.dumps(request, ensure_ascii=False), time.time()))
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),'QUEUED','Job queued'))
    return get(jid)


def get(jid):
    with connect() as db:
        return decode(db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone(),db)


def operations(jid, limit=200, offset=0):
    with connect() as db:
        rows = db.execute('''SELECT job AS job_id, source_id, stage_id, operation_id, attempt,
                          status, started_at, finished_at, updated_at, processed_units,
                          total_units, unit_type, message, error_code, details
                          FROM job_operations WHERE job=? ORDER BY started_at DESC, rowid DESC
                          LIMIT ? OFFSET ?''', (jid,limit,offset)).fetchall()
    return [{**dict(row), 'details':json.loads(row['details']),
             'elapsed_seconds':round((row['finished_at'] or time.time())-row['started_at'],3)}
            for row in rows]


def record_operation(db, jid, lease, stage, now):
    source = stage.get('source_id') or ''
    key = stage['key']
    operation = stage['operation_id']
    status = stage['status']
    db.execute('''INSERT INTO job_operations
        VALUES(?,?,?,?,?,(SELECT COALESCE(MAX(attempt),0)+1 FROM job_operations
            WHERE job=? AND source_id=? AND stage_id=? AND operation_id=?),?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(job,source_id,stage_id,operation_id,lease) DO UPDATE SET
            status=excluded.status, finished_at=excluded.finished_at, updated_at=excluded.updated_at,
            processed_units=excluded.processed_units, total_units=excluded.total_units,
            unit_type=excluded.unit_type, message=excluded.message, error_code=excluded.error_code,
            details=excluded.details''',
        (jid,source,key,operation,lease,jid,source,key,operation,status,now,
         now if status != 'running' else None,now,stage.get('current'),stage.get('total'),
         stage.get('unit'),stage.get('message'),stage.get('error_code'),json.dumps(stage.get('details') or {})))


def finish_open_operations(db, jid, now, status, error_code=None):
    db.execute('''UPDATE job_operations SET status=?,finished_at=?,updated_at=?,error_code=?
                  WHERE job=? AND status='running' ''', (status,now,now,error_code,jid))


def list_jobs(limit=200,offset=0):
    with connect() as db:
        return [decode(r,db) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT ? OFFSET ?',(min(200,max(1,limit)),max(0,offset))).fetchall()]


def can_claim_remote(payload):
    request = json.loads(payload)
    urls = [item['source'] for item in request.get('sources', [])] or [request['source']]
    return request['save_drive'] and all(not url.startswith('upload:') for url in urls)


def claim(worker, remote=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        expired = db.execute("SELECT id,state,result FROM jobs WHERE lease IS NOT NULL AND seen < ?", (now-120,))
        for item in expired:
            result = json.loads(item['result'])
            # Drive may have accepted a write before the worker lost its lease.
            retryable = item['state'] != 'UPLOADING' or bool(result.get('cloud_verified'))
            message = ('Worker lease expired; checkpoints retained' if retryable else
                       'Worker lease expired during upload; inspect remote outputs before retry')
            failure = {'code':'WORKER_LEASE_EXPIRED','stage':result.get('active_stage') or item['state'],
                       'message':message,'retryable':retryable}
            state = schedule_retry(result, failure, now) if retryable else 'BLOCKED'
            result['failure'] = failure
            db.execute('UPDATE jobs SET state=?,error=?,result=?,lease=NULL,seen=? WHERE id=?',
                       (state,message,json.dumps(result,ensure_ascii=False),now,item['id']))
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(item['id'],now,state,message))
            db.execute("UPDATE job_stages SET status='failed',finished=?,message=? WHERE job=? AND status='running'",(now,message,item['id']))
            finish_open_operations(db,item['id'],now,'failed',failure['code'])
        if db.execute('SELECT 1 FROM jobs WHERE worker=? AND lease IS NOT NULL',(worker,)).fetchone():
            return None
        rows = db.execute("""SELECT id,request FROM jobs WHERE state='QUEUED' AND cancelled=0
                          AND coalesce(json_extract(result,'$.retry_at'),0)<=? ORDER BY created""", (now,))
        row = next((r for r in rows if not remote or can_claim_remote(r['request'])),None)
        if not row:
            return None
        lease = uuid.uuid4().hex
        db.execute("UPDATE jobs SET state='PROBING',error=NULL,worker=?,lease=?,seen=?,result=json_remove(result,'$.retry_at') WHERE id=?", (worker,lease,now,row['id']))
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(row['id'],time.time(),'PROBING','Lease assigned to '+worker))
        usage = db.execute('''SELECT
            COALESCE(SUM(json_extract(details,'$.model_type')='text'),0) AS text,
            COALESCE(SUM(json_extract(details,'$.model_type')='visual'),0) AS visual,
            COALESCE(SUM(json_extract(details,'$.context_window')),0) AS context,
            COALESCE(SUM(json_extract(details,'$.output_token_limit')),0) AS output,
            COALESCE(SUM(finished_at-started_at),0) AS seconds
            FROM job_operations WHERE job=? AND json_extract(details,'$.model_type') IS NOT NULL''', (row['id'],)).fetchone()
        return {'job': decode(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone()),
                'lease': lease,'model_usage':dict(usage)}


def schedule_retry(result, failure, now):
    used = result.get('automatic_retries', 0)
    failure.update(attempt=used+1, max_attempts=config.AUTOMATIC_RETRIES+1)
    if used >= config.AUTOMATIC_RETRIES:
        return 'FAILED'
    result['automatic_retries'] = used+1
    result['retry_at'] = now + (30 if failure['code']=='DOWNLOAD_RATE_LIMITED' else 5) * 2**used
    return 'QUEUED'


def update(jid, lease, state=None, result=None, error=None, current=None, total=None,stage_update=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM jobs WHERE id=? AND lease=?', (jid,lease)).fetchone()
        if not row or row['cancelled']:
            raise InterruptedError('Job cancelled or worker lease lost')
        value = json.loads(row['result'])
        if result:
            result=json.loads(json.dumps(result,ensure_ascii=False))
            for index,output in enumerate(result.get('outputs',[])):
                metadata=output.get('publishing_metadata')
                if metadata:
                    provenance=metadata.pop('_provenance',{})
                    db.execute('INSERT OR IGNORE INTO metadata_versions VALUES(?,?,?,?,?,?,?)',(jid,index,metadata['version'],json.dumps(metadata,ensure_ascii=False),json.dumps(provenance,ensure_ascii=False),time.time(),0))
            value.update(result)
        if state=='QUEUED':
            failure=value.get('failure')
            if row['state']=='UPLOADING' or not failure or not failure.get('retryable'):
                raise ValueError('Automatic retry requires a retryable processing failure')
            state=schedule_retry(value,failure,time.time())
        if state=='READY':
            value.pop('failure',None)
        if state is None:
            if current is None:
                current=row['current']
            if total is None:
                total=row['total']
        terminal = state in ('READY','FAILED','BLOCKED','CANCELLED','QUEUED','REVIEW')
        db.execute('UPDATE jobs SET state=?,result=?,error=?,current=?,total=?,seen=?,lease=? WHERE id=?',
                   (state or row['state'], json.dumps(value, ensure_ascii=False), error,current,total,time.time(),None if terminal else lease,jid))
        db.execute('UPDATE workers SET seen=? WHERE id=?',(time.time(),row['worker']))
        if state and (state!=row['state'] or error):
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),state,error))
        if stage_update:
            s=stage_update
            status=s.get('status','running')
            if status not in ('running','completed','skipped','failed','pending'):
                raise ValueError('Invalid stage status')
            now=time.time()
            if s.get('operation_id'):
                record_operation(db,jid,lease,{**s,'status':status},now)
            if s.get('project',True):
                db.execute('''INSERT INTO job_stages VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(job,key) DO UPDATE SET status=excluded.status,
                    started=CASE WHEN job_stages.finished IS NOT NULL THEN excluded.started ELSE job_stages.started END,
                    finished=excluded.finished,current=excluded.current,total=excluded.total,
                    unit=excluded.unit,message=excluded.message''',
                    (jid,s['key'],status,now,now if status in ('completed','skipped','failed') else None,
                     s.get('current'),s.get('total'),s.get('unit'),s.get('message')))
        if terminal:
            now=time.time()
            failure=value.get('failure') or {}
            status='cancelled' if state=='CANCELLED' else 'failed' if state in ('FAILED','BLOCKED','QUEUED') else 'skipped'
            finish_open_operations(db,jid,now,status,failure.get('code'))
            db.execute("UPDATE job_stages SET status=?,finished=? WHERE job=? AND status='running'",(status,now,jid))


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
        now=time.time()
        cur=db.execute("UPDATE jobs SET cancelled=1,state='CANCELLED',lease=NULL,seen=? WHERE id=? AND state NOT IN ('READY','PUBLISHED','CANCELLED')", (now,jid))
        if cur.rowcount:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,now,'CANCELLED','Cancelled by operator'))
            finish_open_operations(db,jid,now,'cancelled','OPERATOR_CANCELLED')
            db.execute("UPDATE job_stages SET status='cancelled',finished=? WHERE job=? AND status='running'",(now,jid))


def retry(jid):
    with connect() as db:
        # A retry resumes files/checkpoints; verified Drive outputs are retained.
        cur = db.execute("""UPDATE jobs SET state='QUEUED',error=NULL,cancelled=0,lease=NULL,
                         result=json_remove(result,'$.automatic_retries','$.retry_at','$.failure')
                         WHERE id=? AND state IN ('FAILED','BLOCKED','CANCELLED')""", (jid,))
        if cur.rowcount:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),'QUEUED','Manual retry; checkpoints retained'))
        return cur.rowcount == 1


def edit_plan(jid, revision, edits, target, approve=False):
    from .assets import asset_path
    from .models import JobRequest
    from .render_timeline import build, compile_scenes, validate_scene_edits

    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state,request,result FROM jobs WHERE id=?',(jid,)).fetchone()
        if row is None:
            raise KeyError(jid)
        result = json.loads(row['result'])
        plan = result.get('edit_plan')
        request = JobRequest.model_validate_json(row['request'])
        revising_local_output = row['state']=='READY' and not request.save_drive
        if (row['state']!='REVIEW' and not revising_local_output) or not plan or plan['revision']!=revision:
            raise InterruptedError('The edit plan changed or was submitted. Reload and try again.')
        limits = {item.source_id:item for item in request.sources}
        contributions = defaultdict(float)
        original = {segment['id']:segment for segment in plan['segments']}
        if len({edit['id'] for edit in edits})!=len(edits):
            raise ValueError('Choose each segment at most once')
        selected = []
        for edit in edits:
            segment = original.get(edit['id'])
            if segment is None:
                raise ValueError('Unknown segment in edit plan')
            start,end = edit['start_seconds'],edit['end_seconds']
            source = plan['sources'][segment['source_id']]
            if not request.minimum<=end-start<=request.maximum or end+segment['source_offset']>source['end']+1e-8:
                raise ValueError(f'Segment {edit["id"]}: choose a range within the source and the clip duration limits')
            source_id = segment['source_id']
            options = limits.get(source_id)
            if options:
                offset = segment['source_offset']
                if any(end+offset>a and start+offset<b for a,b in options.exclude):
                    raise ValueError(f'Segment {edit["id"]}: the edit overlaps an excluded source interval')
                contributions[source_id]+=end-start
                if options.max_contribution is not None and contributions[source_id]>options.max_contribution+1e-8:
                    raise ValueError(f'Segment {edit["id"]}: the source exceeds its maximum contribution')
            selected.append({**segment,**edit})
            validate_scene_edits(selected[-1],end-start)
            for effect in selected[-1].get('effects', []):
                library = {'image_overlay':'logos','video_overlay':'backgrounds'}.get(effect['kind'])
                if library:
                    asset_path(library,effect['asset'])
            for track in ('sounds','effects'):
                if track in selected[-1]:
                    selected[-1][track] = [{**event,'id':event.get('id') or uuid.uuid4().hex}
                                           for event in selected[-1][track]]
            if (start,end)!=(segment['start_seconds'],segment['end_seconds']):
                selected[-1].update(selection_method='manual_boundaries',reason='Boundaries edited by the operator')
                selected[-1].pop('score',None)
                for marker in ('event_seconds','payoff_seconds'):
                    timestamp=selected[-1].get(marker)
                    if timestamp is not None and not start<=timestamp<end:
                        selected[-1].pop(marker)
                if 'narrative_event' in selected[-1]:
                    from .compilation import gameplay_event
                    selected[-1]['narrative_event'] = gameplay_event(selected[-1])
        if target is not None and request.workflow!='compilation':
            raise ValueError('A timeline target is available for compilations')
        plan.update(revision=revision+1,segments=selected,approved=approve)
        if target is not None:
            plan['target_duration']=target
        timeline = build(selected,request,{key:source['end'] for key,source in plan['sources'].items()},
                         plan['revision'],plan['target_duration'])
        compile_scenes(timeline,request)
        if revising_local_output:
            result['previous_timeline_outputs'] = result.pop('outputs',[])
            result.pop('clips_completed',None)
            result.pop('publishing_state',None)
        if approve:
            result['render_timeline'] = timeline
        else:
            result.pop('render_timeline',None)
        state = 'QUEUED' if approve else 'REVIEW'
        db.execute('UPDATE jobs SET state=?,result=?,seen=? WHERE id=?',
                   (state,json.dumps(result,ensure_ascii=False),time.time(),jid))
        if approve:
            db.execute('INSERT INTO events VALUES(?,?,?,?)',(jid,time.time(),state,'Edit plan approved for rendering'))
        return plan


def approve(jid,index,value):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT state,result FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row or row['state']!='READY':
            raise ValueError('Only a completed output can be approved')
        result=json.loads(row['result'])
        editorial=result['outputs'][index].get('editorial',{})
        if value and editorial.get('technical_valid') is False:raise ValueError('Hard technical validations failed; re-render before approval')
        if value and editorial.get('status')=='REJECTED':raise ValueError('Rejected or duplicate output cannot be approved; create a corrected version')
        result['outputs'][index]['approved']=value
        result['outputs'][index]['approved_render_id']=result['outputs'][index].get('render_id') if value else None
        if editorial:
            editorial['human_reviewed']=bool(value)
            editorial['status']='READY_FOR_PUBLISHING' if value and result.get('cloud_verified') else 'APPROVED' if value else 'NEEDS_REVIEW' if editorial.get('issues') else 'READY_FOR_REVIEW'
        db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),jid))
        if not value:
            db.execute("UPDATE publications SET state='DRAFT',error='Approval withdrawn; review and queue again' WHERE job=? AND output=? AND state IN ('QUEUED','FAILED','RETRYING') AND session IS NULL AND video_id IS NULL",(jid,index))


def metadata_history(jid,index):
    with connect() as db:
        return [{'version':r['version'],'metadata':json.loads(r['metadata']),'provenance':json.loads(r['provenance']),'created':r['created'],'manual':bool(r['manual'])} for r in db.execute('SELECT * FROM metadata_versions WHERE job=? AND output=? ORDER BY created DESC',(jid,index))]


def revise_metadata(jid,index,metadata,manual=True):
    """A revision invalidates old approval; queued remote effects are immutable."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT state,result FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row or row['state']!='READY':raise ValueError('Only completed outputs can be edited')
        if db.execute("SELECT 1 FROM publications WHERE job=? AND output=? AND (session IS NOT NULL OR video_id IS NOT NULL OR state='PUBLISHING')",(jid,index)).fetchone():raise ValueError('Publication already has external effects; its metadata cannot be changed')
        result=json.loads(row['result']);output=result['outputs'][index]
        metadata=json.loads(json.dumps(metadata,ensure_ascii=False));provenance=metadata.pop('_provenance',{})
        db.execute('INSERT INTO metadata_versions VALUES(?,?,?,?,?,?,?)',(jid,index,metadata['version'],json.dumps(metadata,ensure_ascii=False),json.dumps(provenance,ensure_ascii=False),time.time(),int(manual)))
        output['publishing_metadata']=metadata;output['title']=metadata['title'];output['approved']=False
        output['editorial']={**output.get('editorial',{}),'status':'NEEDS_REVIEW','review_required':True,'human_reviewed':False}
        db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),jid))
        # Do not silently change an already reviewed publication. Stop its queue
        # entry until the operator approves/requeues the revised draft.
        db.execute("UPDATE publications SET state='DRAFT',error='Output metadata changed; approve the revision and queue again' WHERE job=? AND output=? AND session IS NULL AND video_id IS NULL",(jid,index))


def preferences(channel):
    with connect() as db:
        row=db.execute('SELECT preferences FROM channel_preferences WHERE channel=?',(channel,)).fetchone()
        return json.loads(row['preferences']) if row else {}


def source_in_use(source,exclude):
    # Never use the paginated UI list to decide whether an original may go away.
    with connect() as db:
        return db.execute("""SELECT 1 FROM jobs WHERE id<>? AND state<>'READY' AND
                            (json_extract(request,'$.source')=? OR EXISTS (
                              SELECT 1 FROM json_each(jobs.request,'$.sources')
                              WHERE json_extract(value,'$.source')=?)) LIMIT 1""",
                          (exclude,source,source)).fetchone() is not None
