"""Direct Drive -> YouTube bounded transfer, review gate and durable idempotency.

No public visibility is possible without a per-channel policy and an explicit
public/scheduled queue request. Uncertain outcomes cannot start a new upload.
"""
import json
import os
from pathlib import Path
import re
import time
import uuid
from datetime import datetime,timezone,timedelta
import httpx
from . import store
from .drive import Drive, BASE, CHUNK, acknowledged

YT='https://www.googleapis.com/youtube/v3'


def token_file(alias):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',alias):
        raise ValueError('Invalid YouTube credential alias')
    root=Path(os.environ.get('YOUTUBE_TOKEN_DIR','secrets/youtube')).resolve()
    path=root/(alias+'.json')
    if not path.is_file():
        raise ValueError('YouTube OAuth missing. Mount the existing authorized-user JSON in YOUTUBE_TOKEN_DIR.')
    return path


def discover_channels():
    root=Path(os.environ.get('YOUTUBE_TOKEN_DIR','secrets/youtube'))
    errors=[]
    for path in root.glob('*.json'):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',path.stem):
            continue
        client=None
        try:
            client=Drive(token_file(path.stem))
            response=client.request('GET',YT+'/channels',params={'part':'snippet','mine':'true'})
            for channel in response.json()['items']:
                with store.connect() as db:
                    db.execute('INSERT INTO channels(id,alias,title) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET alias=excluded.alias,title=excluded.title',(channel['id'],path.stem,channel['snippet']['title']))
        except Exception:
            errors.append({'alias':path.stem,'error':'Authorization/channel lookup failed. Check OAuth scopes, API access and token validity.'})
        finally:
            if client:
                client.close()
    return {'channels':channels(),'errors':errors}


def channels():
    with store.connect() as db:
        return [dict(row) for row in db.execute('SELECT c.*,coalesce(s.interval_minutes,120) interval_minutes FROM channels c LEFT JOIN channel_schedules s ON s.channel=c.id')]


def set_policy(channel,daily_limit,public_allowed,automatic,interval_minutes=120):
    if automatic and not public_allowed:
        raise ValueError('Automatic publishing requires explicit public publishing authorization for this channel')
    with store.connect() as db:
        if not db.execute('UPDATE channels SET daily_limit=?,public_allowed=?,automatic=? WHERE id=?',(daily_limit,public_allowed,automatic,channel)).rowcount:
            raise ValueError('Connect this authorized channel first')
        db.execute('INSERT OR REPLACE INTO channel_schedules VALUES(?,?)',(channel,interval_minutes))


def history():
    with store.connect() as db:
        rows=[]
        for row in db.execute('SELECT * FROM publications ORDER BY created DESC LIMIT 200'):
            value=dict(row)
            value.pop('session',None)
            value['editable']=row['session'] is None and row['state'] in ('QUEUED','FAILED')
            value['metadata']=json.loads(value['metadata'])
            rows.append(value)
        return rows


def enqueue(jid,index,channel,title,description,privacy='private',publish_at=None,automatic=False):
    job=store.get(jid)
    if not job or job['state']!='READY' or index<0:
        raise ValueError('Only READY outputs can be queued')
    try:
        output=job['result']['outputs'][index]
    except (KeyError,IndexError):
        raise ValueError('Output not found') from None
    if not output.get('drive') or not job['result'].get('cloud_verified'):
        raise ValueError('Verify the Drive upload before publishing')
    if not output.get('approved') and not automatic:
        raise ValueError('Approve the output in Editor before publication')
    if privacy not in ('private','public','unlisted'):
        raise ValueError('Invalid privacy mode')
    status={'privacyStatus':privacy,'selfDeclaredMadeForKids':False}
    if publish_at:
        when=datetime.fromisoformat(publish_at.replace('Z','+00:00'))
        if when.tzinfo is None or when<=datetime.now(timezone.utc):
            raise ValueError('Schedule must be a future timezone-aware timestamp')
        status={'privacyStatus':'private','publishAt':when.astimezone(timezone.utc).isoformat(),'selfDeclaredMadeForKids':False}
    snippet={'title':title[:100],'description':description[:5000],'categoryId':'22'}
    language=job['result'].get('language')
    if language:
        snippet['defaultLanguage']=language
        snippet['defaultAudioLanguage']=language
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        policy=db.execute('SELECT * FROM channels WHERE id=?',(channel,)).fetchone()
        if not policy:
            raise ValueError('Select an authenticated YouTube channel')
        if (privacy=='public' or publish_at) and not policy['public_allowed']:
            raise ValueError('Public publishing has not been explicitly enabled for this channel')
        if automatic and not policy['automatic']:
            raise ValueError('Automatic mode has not been enabled for this channel')
        prior=db.execute('SELECT id FROM publications WHERE job=? AND output=? AND channel=?',(jid,index,channel)).fetchone()
        if prior:
            return prior['id']
        if automatic and not publish_at:
            cadence=db.execute('SELECT interval_minutes FROM channel_schedules WHERE channel=?',(channel,)).fetchone()
            minutes=cadence['interval_minutes'] if cadence else 120
            planned=[]
            for row in db.execute('SELECT metadata FROM publications WHERE channel=?',(channel,)):
                scheduled=json.loads(row['metadata'])['status'].get('publishAt')
                if scheduled:
                    planned.append(datetime.fromisoformat(scheduled.replace('Z','+00:00')))
            next_time=max(datetime.now(timezone.utc)+timedelta(hours=2),max(planned,default=datetime.now(timezone.utc))+timedelta(minutes=minutes))
            for _ in range(1000):
                if sum(t.date()==next_time.date() for t in planned)<policy['daily_limit']:
                    break
                next_time+=timedelta(minutes=minutes)
            status={'privacyStatus':'private','publishAt':next_time.isoformat(),'selfDeclaredMadeForKids':False}
        pid=uuid.uuid4().hex
        metadata={'snippet':snippet,'status':status,'drive':output['drive'],'automatic':automatic}
        db.execute('INSERT INTO publications(id,job,output,channel,state,metadata,created) VALUES(?,?,?,?,?,?,?)',(pid,jid,index,channel,'QUEUED',json.dumps(metadata,ensure_ascii=False),time.time()))
        return pid


def claim():
    now=time.time()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # A process can resume only the saved session, never insert a second video.
        db.execute("UPDATE publications SET state=CASE WHEN session IS NULL THEN 'FAILED' ELSE 'RETRYING' END,error='Publisher restarted; retry the saved session',seen=? WHERE state='PUBLISHING' AND seen<?",(now,now-180))
        for row in db.execute("SELECT p.*,c.alias,c.daily_limit FROM publications p JOIN channels c ON c.id=p.channel WHERE p.state='QUEUED' OR (p.state='RETRYING' AND (p.seen IS NULL OR p.seen<?)) ORDER BY p.created",(now-30,)).fetchall():
            day=now-now%86400
            used=db.execute("SELECT count(*) FROM publications WHERE channel=? AND state IN ('PUBLISHED','SCHEDULED','PUBLISHING') AND seen>=?",(row['channel'],day)).fetchone()[0]
            if used>=row['daily_limit']:
                continue
            db.execute("UPDATE publications SET state='PUBLISHING',seen=?,attempts=attempts+1,error=NULL WHERE id=?",(now,row['id']))
            return dict(row)


def checkpoint(pid,**fields):
    allowed={'state','session','video_id','current','total','error'}
    if not set(fields)<=allowed:
        raise ValueError('Invalid publication checkpoint')
    with store.connect() as db:
        pairs=','.join(k+'=?' for k in fields)
        db.execute('UPDATE publications SET '+pairs+',seen=? WHERE id=?',(*fields.values(),time.time(),pid))


def retry(pid):
    with store.connect() as db:
        # UNCERTAIN requires remote reconciliation, never an automatic new insert.
        return bool(db.execute("UPDATE publications SET state='RETRYING',seen=NULL WHERE id=? AND state IN ('FAILED','RETRYING')",(pid,)).rowcount)


def validate_session(url):
    if not url.startswith('https://www.googleapis.com/'):
        raise ValueError('Invalid upload session destination')


class Uncertain(ValueError):
    pass


def upload(publication):
    pid=publication['id']
    youtube=None
    drive=None
    try:
        youtube=Drive(token_file(publication['alias']))
        authorized=youtube.request('GET',YT+'/channels',params={'part':'id','mine':'true'}).json()['items']
        if publication['channel'] not in [c['id'] for c in authorized]:
            raise ValueError('OAuth token is authorized for a different channel; nothing uploaded')
        drive=Drive()
        body=json.loads(publication['metadata'])
        remote=body.pop('drive')
        automatic=body.pop('automatic',False)
        with store.connect() as db:
            policy=db.execute('SELECT * FROM channels WHERE id=?',(publication['channel'],)).fetchone()
            if not policy or ((body['status']['privacyStatus']=='public' or body['status'].get('publishAt')) and not policy['public_allowed']) or (automatic and not policy['automatic']):
                raise ValueError('Publishing policy was revoked; nothing uploaded')
        scheduled=body['status'].get('publishAt')
        if scheduled and datetime.fromisoformat(scheduled.replace('Z','+00:00'))<=datetime.now(timezone.utc):
            if publication['session']:
                raise Uncertain('Schedule elapsed during an upload session; reconcile remotely before continuing')
            if not automatic:
                raise ValueError('Scheduled time has elapsed; edit the queue item before upload')
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                cadence=db.execute('SELECT interval_minutes FROM channel_schedules WHERE channel=?',(publication['channel'],)).fetchone()
                minutes=cadence['interval_minutes'] if cadence else 120
                planned=[]
                for row in db.execute('SELECT metadata FROM publications WHERE channel=? AND id<>?',(publication['channel'],pid)):
                    when=json.loads(row['metadata'])['status'].get('publishAt')
                    if when:
                        planned.append(datetime.fromisoformat(when.replace('Z','+00:00')))
                next_time=max(datetime.now(timezone.utc)+timedelta(hours=2),max(planned,default=datetime.now(timezone.utc))+timedelta(minutes=minutes))
                for _ in range(1000):
                    if sum(t.date()==next_time.date() for t in planned)<policy['daily_limit']:
                        break
                    next_time+=timedelta(minutes=minutes)
                body['status']['publishAt']=next_time.isoformat()
                db.execute('UPDATE publications SET metadata=? WHERE id=?',(json.dumps({**body,'drive':remote,'automatic':automatic},ensure_ascii=False),pid))
        file_id=remote['id']
        verified=drive.request('GET',BASE+'/files/'+file_id,params={'fields':'id,size,md5Checksum','supportsAllDrives':'true'}).json()
        if verified.get('md5Checksum')!=remote.get('md5Checksum') or verified.get('size')!=remote.get('size'):
            raise ValueError('Drive artifact changed after verification; publication blocked')
        total=int(verified['size'])
        checkpoint(pid,total=total)
        session=publication['session']
        offset=0
        response=None
        if session:
            validate_session(session)
            response=youtube.client.put(session,headers={'Content-Length':'0','Content-Range':f'bytes */{total}'},content=b'')
            if response.status_code in (200,201):
                complete(pid,response.json(),body,youtube,publication['channel'])
                return
            if response.status_code in (404,410):
                raise Uncertain('Upload session expired; reconcile with YouTube Studio before any new upload')
            if response.status_code!=308:
                raise ValueError(f'YouTube session query failed ({response.status_code}); retry the existing session')
            offset=acknowledged(response)
        else:
            response=youtube.client.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status'},json=body,headers={'X-Upload-Content-Length':str(total),'X-Upload-Content-Type':'video/mp4'})
            if response.status_code not in (200,201):
                raise ValueError(f'YouTube session creation failed ({response.status_code}); check OAuth scopes, quota and API project status')
            session=response.headers['Location']
            validate_session(session)
            checkpoint(pid,session=session)
        while offset<total:
            end=min(offset+CHUNK,total)-1
            # Bound memory even if Drive ignores Range. Never materialize a full MP4.
            with drive.client.stream('GET',BASE+'/files/'+file_id,params={'alt':'media','supportsAllDrives':'true'},headers={'Range':f'bytes={offset}-{end}'}) as source:
                if source.status_code!=206:
                    raise ValueError('Drive did not honor a bounded Range request; upload stopped without a local copy')
                if source.headers.get('Content-Range')!=f'bytes {offset}-{end}/{total}':
                    raise ValueError('Drive returned an unexpected byte range')
                content=bytearray()
                for chunk in source.iter_bytes(256*1024):
                    if len(content)+len(chunk)>CHUNK:
                        raise ValueError('Drive response exceeded the bounded transfer size')
                    content.extend(chunk)
                if len(content)!=end-offset+1:
                    raise ValueError('Drive returned an incomplete chunk; retry the saved upload session')
            response=youtube.client.put(session,content=bytes(content),headers={'Content-Type':'video/mp4','Content-Length':str(len(content)),'Content-Range':f'bytes {offset}-{end}/{total}'})
            if response.status_code in (200,201):
                complete(pid,response.json(),body,youtube,publication['channel'])
                return
            if response.status_code!=308:
                raise ValueError(f'YouTube chunk upload failed ({response.status_code}); retry the existing session')
            next_offset=acknowledged(response)
            if next_offset<=offset or next_offset>total:
                raise ValueError('YouTube upload acknowledgment made no valid progress')
            offset=next_offset
            checkpoint(pid,current=offset)
        raise Uncertain('All bytes acknowledged without a video ID; reconcile the existing session')
    except Uncertain as error:
        checkpoint(pid,state='UNCERTAIN',error=str(error))
    except (httpx.HTTPError,ValueError,KeyError,OSError):
        # A retry will query the persisted session first, including after final PUT timeout.
        checkpoint(pid,state='FAILED',error='Upload interrupted or authorization/quota validation failed. Retry resumes the saved session; check channel authorization and Drive access.')
    finally:
        if drive:
            drive.close()
        if youtube:
            youtube.close()


def complete(pid,response,metadata,youtube,channel):
    if not response.get('id'):
        raise Uncertain('YouTube returned no video ID; reconcile the existing session')
    # Persist identity before verification: a verification outage must never
    # erase knowledge of a remotely created video.
    checkpoint(pid,video_id=response['id'])
    remote=youtube.request('GET',YT+'/videos',params={'part':'snippet,status','id':response['id']}).json()['items']
    if not remote or remote[0]['snippet']['channelId']!=channel or remote[0]['status']['privacyStatus']!=metadata['status']['privacyStatus']:
        raise Uncertain('Video ID exists but channel/privacy verification failed; inspect YouTube Studio')
    if metadata['status'].get('publishAt') and not remote[0]['status'].get('publishAt'):
        raise Uncertain('Video ID exists but native schedule was not confirmed; inspect YouTube Studio')
    with store.connect() as db:
        total=db.execute('SELECT total FROM publications WHERE id=?',(pid,)).fetchone()['total']
    checkpoint(pid,state='SCHEDULED' if metadata['status'].get('publishAt') else 'PUBLISHED',video_id=response['id'],current=total)


def loop(stop):
    while not stop.is_set():
        auto_queue()
        publication=claim()
        if publication:
            upload(publication)
        else:
            stop.wait(5)


def auto_queue():
    """Reconcile READY automatic jobs after restarts; enqueue remains idempotent."""
    for job in store.list_jobs():
        if job['state']!='READY' or not job['request'].get('publish_automatic'):
            continue
        channel=job['request'].get('publish_channel')
        try:
            for index,output in enumerate(job['result'].get('outputs',[])):
                enqueue(job['id'],index,channel,output['title'][:100],job['result'].get('source',{}).get('title',''),automatic=True)
        except ValueError:
            # A revoked policy does not change READY rendering state or publish.
            continue
