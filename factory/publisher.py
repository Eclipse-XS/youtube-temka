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
            value['editable']=row['session'] is None and row['video_id'] is None and row['state'] in ('QUEUED','FAILED')
            value['metadata']=json.loads(value['metadata'])
            rows.append(value)
        return rows


def publication_status(privacy,publish_at):
    if privacy not in ('private','public','unlisted'):
        raise ValueError('Invalid privacy mode')
    status={'privacyStatus':privacy,'selfDeclaredMadeForKids':False}
    if publish_at:
        when=datetime.fromisoformat(publish_at.replace('Z','+00:00'))
        if when.tzinfo is None or when<=datetime.now(timezone.utc):
            raise ValueError('Schedule must be a future timezone-aware timestamp')
        status={'privacyStatus':'private','publishAt':when.astimezone(timezone.utc).isoformat(),'selfDeclaredMadeForKids':False}
    return status


def credited_description(description,attribution):
    """Preserve the operator's explicit credit, including when metadata is edited."""
    credit=(attribution or '').strip()
    if credit and credit not in description:
        description=(description.rstrip()+'\n\n' if description.strip() else '')+credit
    if len(description.encode('utf-8'))>5000:
        raise ValueError('YouTube descriptions, including source credit, are limited to 5000 UTF-8 bytes. Shorten the description.')
    if '<' in description or '>' in description:
        raise ValueError('YouTube descriptions cannot contain < or >. Remove HTML markup.')
    return description


def valid_title(title):
    if not title.strip() or len(title)>100 or '<' in title or '>' in title:
        raise ValueError('Provide a nonempty title up to 100 characters without < or >')
    return title


def needs_editorial_review(job,index):
    candidates=job['result'].get('candidates',[])
    selected=candidates if job['request'].get('mode')=='longs' else candidates[index:index+1]
    return any(c.get('editorial_review_required') or c.get('selection_method')=='heuristic' or c.get('score',100)<50 or c.get('confidence',1)<.6 for c in selected)


def edit(pid,title,description,privacy='private',publish_at=None):
    """Edit only before remote effects; an expired schedule can be corrected safely."""
    status=publication_status(privacy,publish_at)
    valid_title(title)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM publications WHERE id=?',(pid,)).fetchone()
        if not row or row['state'] not in ('QUEUED','FAILED') or row['session'] or row['video_id']:
            raise ValueError('Only queued/failed items without an upload session or video ID can be edited')
        policy=db.execute('SELECT * FROM channels WHERE id=?',(row['channel'],)).fetchone()
        if not policy or ((privacy=='public' or publish_at) and not policy['public_allowed']):
            raise ValueError('Public publishing has not been explicitly enabled for this channel')
        metadata=json.loads(row['metadata'])
        job=db.execute('SELECT request FROM jobs WHERE id=?',(row['job'],)).fetchone()
        attribution=json.loads(job['request']).get('source_attribution','') if job else ''
        metadata['snippet'].update(title=title,description=credited_description(description,attribution))
        metadata['status']=status
        metadata['automatic']=False
        db.execute("UPDATE publications SET metadata=?,state='QUEUED',error=NULL WHERE id=?",(json.dumps(metadata,ensure_ascii=False),pid))


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
    if automatic and not output.get('approved') and needs_editorial_review(job,index):
        raise ValueError('Weak or ungrounded selection requires editorial approval before automatic publication')
    status=publication_status(privacy,publish_at)
    snippet={'title':valid_title(title[:100]),'description':credited_description(description,job['request'].get('source_attribution','')),'categoryId':'22'}
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


class PublicationError(ValueError):
    pass


def upload_error(response,operation):
    """Expose known API reasons, never raw Google payloads or session URLs."""
    reasons={
        'quotaExceeded':'YouTube API quota is exhausted; wait for its reset',
        'dailyLimitExceeded':'YouTube API daily limit is exhausted; wait for its reset',
        'uploadLimitExceeded':'This channel reached its upload limit; wait before retrying',
        'insufficientPermissions':'Reauthorize this channel with youtube.upload and youtube.readonly scopes',
        'forbidden':'The API project or channel does not permit this upload; check authorization',
        'invalidTitle':'Correct the title before retrying',
        'invalidDescription':'Correct the description before retrying; maximum 5000 UTF-8 bytes and no HTML angle brackets',
        'invalidPublishAt':'Correct the future publication time before retrying',
    }
    try:reason=response.json()['error']['errors'][0]['reason']
    except (ValueError,KeyError,IndexError,TypeError):reason=None
    advice=reasons.get(reason,'Check channel authorization, API project access and network connectivity')
    return PublicationError(f'{operation} failed (HTTP {response.status_code}). {advice}. Existing upload identity is preserved.')


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
        if publication.get('video_id'):
            # A returned video identity is authoritative even if a later GET failed.
            # Reconcile it directly; never depend on a possibly expired session.
            complete(pid,{'id':publication['video_id']},body,youtube,publication['channel'])
            return
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
                raise upload_error(response,'YouTube session query')
            offset=acknowledged(response)
        else:
            response=youtube.client.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status'},json=body,headers={'X-Upload-Content-Length':str(total),'X-Upload-Content-Type':'video/mp4'})
            if response.status_code not in (200,201):
                raise upload_error(response,'YouTube session creation')
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
                raise upload_error(response,'YouTube chunk upload')
            next_offset=acknowledged(response)
            if next_offset<=offset or next_offset>total:
                raise ValueError('YouTube upload acknowledgment made no valid progress')
            offset=next_offset
            checkpoint(pid,current=offset)
        raise Uncertain('All bytes acknowledged without a video ID; reconcile the existing session')
    except Uncertain as error:
        checkpoint(pid,state='UNCERTAIN',error=str(error))
    except PublicationError as error:
        checkpoint(pid,state='FAILED',error=str(error))
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
    if remote[0]['status'].get('uploadStatus') not in ('uploaded','processed'):
        raise Uncertain('Video ID exists but YouTube did not confirm a successful upload status; inspect YouTube Studio')
    expected=metadata['status'].get('publishAt')
    if expected:
        actual=remote[0]['status'].get('publishAt')
        if not actual or datetime.fromisoformat(actual.replace('Z','+00:00'))!=datetime.fromisoformat(expected.replace('Z','+00:00')):
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
                if not output.get('approved') and needs_editorial_review(job,index):continue
                enqueue(job['id'],index,channel,output['title'][:100],job['result'].get('source',{}).get('title',''),automatic=True)
        except ValueError:
            # A revoked policy does not change READY rendering state or publish.
            continue
