"""Fixture-only YouTube protocol tests. No remote video is created."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from factory import config, store, publisher


@pytest.fixture
def ready(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'db.sqlite3')
    data=b'0123456789abc'
    remote={'id':'drive-fixture','size':str(len(data)),'md5Checksum':hashlib.md5(data).hexdigest()}
    job=store.create({'source':'upload:fixture.mp4'})
    lease=store.claim('test')['lease']
    store.update(job['id'],lease,state='READY',result={'outputs':[{'name':'clip.mp4','title':'Fixture','approved':True,'drive':remote}],'cloud_verified':True,'language':'en'})
    with store.connect() as db:
        db.execute('INSERT INTO channels(id,alias,title) VALUES(?,?,?)',('channel-fixture','credential-fixture','Fixture Channel'))
    return job['id'],data,remote


def test_review_and_public_policy_are_required(ready):
    jid,_,_=ready
    with pytest.raises(ValueError,match='Public publishing'):
        publisher.enqueue(jid,0,'channel-fixture','Title','','public')
    store.approve(jid,0,False)
    with pytest.raises(ValueError,match='Approve'):
        publisher.enqueue(jid,0,'channel-fixture','Title','')
    with pytest.raises(ValueError,match='Automatic mode'):
        publisher.enqueue(jid,0,'channel-fixture','Title','',automatic=True)


def test_concurrent_queue_requests_create_one_publication(ready):
    jid,_,_=ready
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids=list(pool.map(lambda _:publisher.enqueue(jid,0,'channel-fixture','Title',''),range(6)))
    assert len(set(ids))==1
    assert len(publisher.history())==1
    assert 'session' not in publisher.history()[0]


def install_transport(monkeypatch,data,remote,final_timeout=False,expired=False,wrong_channel=False):
    calls={'insert':0,'range':[],'put':0,'finished':False}
    monkeypatch.setattr(publisher,'CHUNK',8)
    monkeypatch.setattr(publisher,'token_file',lambda alias:alias)
    def handler(request):
        path=request.url.path
        if path.endswith('/channels'):
            return httpx.Response(200,json={'items':[{'id':'wrong' if wrong_channel else 'channel-fixture'}]})
        if path.endswith('/videos') and request.method=='GET':
            return httpx.Response(200,json={'items':[{'snippet':{'channelId':'channel-fixture'},'status':{'privacyStatus':'private','uploadStatus':'uploaded'}}]})
        if path.endswith('/videos') and request.method=='POST':
            calls['insert']+=1
            return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/fixture'})
        if path.endswith('/files/drive-fixture') and 'alt' not in request.url.params:
            return httpx.Response(200,json=remote)
        if path.endswith('/files/drive-fixture'):
            a,b=map(int,request.headers['Range'].removeprefix('bytes=').split('-'))
            calls['range'].append((a,b))
            return httpx.Response(206,content=data[a:b+1],headers={'Content-Range':f'bytes {a}-{b}/{len(data)}'})
        if request.method=='PUT':
            if not request.content:
                if expired:
                    return httpx.Response(404)
                if calls['finished']:
                    return httpx.Response(201,json={'id':'youtube-fixture'})
                return httpx.Response(308)
            calls['put']+=1
            if request.headers['Content-Range'].split('/')[0].endswith(str(len(data)-1)):
                calls['finished']=True
                if final_timeout:
                    raise httpx.ReadTimeout('final response lost',request=request)
                return httpx.Response(201,json={'id':'youtube-fixture'})
            return httpx.Response(308,headers={'Range':'bytes=0-7'})
        raise AssertionError((request.method,str(request.url)))
    class Google:
        def __init__(self,*_):
            self.client=httpx.Client(transport=httpx.MockTransport(handler))
        def request(self,*a,**kw):
            result=self.client.request(*a,**kw)
            result.raise_for_status()
            return result
        def close(self):
            self.client.close()
    monkeypatch.setattr(publisher,'Drive',Google)
    return calls


def test_bounded_drive_to_private_youtube_and_remote_verification(ready,monkeypatch):
    jid,data,remote=ready
    calls=install_transport(monkeypatch,data,remote)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.upload(publisher.claim())
    record=publisher.history()[0]
    assert record['id']==pid
    assert record['state']=='PUBLISHED'
    assert record['video_id']=='youtube-fixture'
    assert record['current']==len(data)
    assert calls['range']==[(0,7),(8,12)]
    assert calls['insert']==1


def test_lost_final_response_reconciles_saved_session_without_reinsert(ready,monkeypatch):
    jid,data,remote=ready
    calls=install_transport(monkeypatch,data,remote,final_timeout=True)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.upload(publisher.claim())
    assert publisher.history()[0]['state']=='FAILED'
    assert publisher.retry(pid)
    publisher.upload(publisher.claim())
    assert publisher.history()[0]['video_id']=='youtube-fixture'
    assert calls['insert']==1
    assert calls['put']==2


def test_expired_session_is_uncertain_and_never_reinserted(ready,monkeypatch):
    jid,data,remote=ready
    calls=install_transport(monkeypatch,data,remote,expired=True)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.checkpoint(pid,session='https://www.googleapis.com/upload/fixture')
    publisher.upload(publisher.claim())
    assert publisher.history()[0]['state']=='UNCERTAIN'
    assert not publisher.retry(pid)
    assert calls['insert']==0


def test_different_authorized_channel_cannot_receive_output(ready,monkeypatch):
    jid,data,remote=ready
    calls=install_transport(monkeypatch,data,remote,wrong_channel=True)
    publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.upload(publisher.claim())
    assert publisher.history()[0]['state']=='FAILED'
    assert calls['insert']==0


def test_automatic_queue_requires_explicit_policy_and_respects_daily_slots(ready):
    jid,_,_=ready
    with pytest.raises(ValueError,match='explicit public'):
        publisher.set_policy('channel-fixture',2,False,True)
    publisher.set_policy('channel-fixture',2,True,True,120)
    with store.connect() as db:
        row=db.execute('SELECT request,result FROM jobs WHERE id=?',(jid,)).fetchone()
        req=json.loads(row['request'])
        req.update(publish_automatic=True,publish_channel='channel-fixture')
        result=json.loads(row['result'])
        result['outputs']=[{**result['outputs'][0],'name':f'clip-{i}.mp4','approved':False} for i in range(5)]
        db.execute('UPDATE jobs SET request=?,result=? WHERE id=?',(json.dumps(req),json.dumps(result),jid))
    publisher.auto_queue()
    publisher.auto_queue()
    records=publisher.history()
    assert len(records)==5
    from collections import Counter
    days=Counter(p['metadata']['status']['publishAt'][:10] for p in records)
    assert max(days.values())<=2
    assert all(p['metadata']['status']['privacyStatus']=='private' for p in records)
    assert all(p['metadata']['automatic'] for p in records)


def test_revoked_public_policy_blocks_a_queued_public_upload(ready,monkeypatch):
    jid,data,remote=ready
    publisher.set_policy('channel-fixture',3,True,False)
    publisher.enqueue(jid,0,'channel-fixture','Title','','public')
    publisher.set_policy('channel-fixture',3,False,False)
    calls=install_transport(monkeypatch,data,remote)
    publisher.upload(publisher.claim())
    assert calls['insert']==0
    assert publisher.history()[0]['state']=='FAILED'


def test_known_video_id_reconciles_without_reopening_upload_session(ready,monkeypatch):
    jid,data,remote=ready
    calls=install_transport(monkeypatch,data,remote,expired=True)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.checkpoint(pid,video_id='youtube-fixture',session='https://www.googleapis.com/upload/fixture',total=len(data))
    publisher.upload(publisher.claim())
    assert publisher.history()[0]['state']=='PUBLISHED'
    assert calls['insert']==calls['put']==0 and calls['range']==[]


def test_wrong_native_schedule_is_uncertain(ready,monkeypatch):
    from datetime import datetime,timezone,timedelta
    jid,_,_=ready
    publisher.set_policy('channel-fixture',3,True,False)
    when=datetime.now(timezone.utc)+timedelta(days=2)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','',publish_at=when.isoformat())
    class YouTube:
        def request(self,*a,**kw):
            return httpx.Response(200,json={'items':[{'snippet':{'channelId':'channel-fixture'},'status':{'privacyStatus':'private','uploadStatus':'uploaded','publishAt':(when+timedelta(hours=1)).isoformat()}}]})
    with pytest.raises(publisher.Uncertain,match='schedule'):
        publisher.complete(pid,{'id':'youtube-fixture'},publisher.history()[0]['metadata'],YouTube(),'channel-fixture')
    assert publisher.history()[0]['video_id']=='youtube-fixture'


def test_expired_queue_item_can_be_corrected_before_remote_effects(ready):
    from datetime import datetime,timezone,timedelta
    jid,_,remote=ready
    pid=publisher.enqueue(jid,0,'channel-fixture','Old title','Old description')
    publisher.checkpoint(pid,state='FAILED',error='Schedule elapsed')
    publisher.set_policy('channel-fixture',3,True,False)
    when=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    publisher.edit(pid,'New title','New description',publish_at=when)
    row=publisher.history()[0]
    assert row['state']=='QUEUED' and row['error'] is None
    assert row['metadata']['snippet']['title']=='New title'
    assert row['metadata']['status']['publishAt']==when
    assert row['metadata']['drive']==remote
    assert row['metadata']['automatic'] is False


@pytest.mark.parametrize('effect',[{'session':'https://www.googleapis.com/upload/fixture'},{'video_id':'youtube-fixture'},{'state':'PUBLISHING'},{'state':'UNCERTAIN'}])
def test_remote_effects_or_active_claim_block_queue_edits(ready,effect):
    jid,_,_=ready
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    publisher.checkpoint(pid,**effect)
    with pytest.raises(ValueError,match='can be edited'):publisher.edit(pid,'Changed','')


def test_queue_edit_cannot_bypass_public_policy(ready):
    jid,_,_=ready
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    with pytest.raises(ValueError,match='Public publishing'):publisher.edit(pid,'Title','','public')
    with pytest.raises(ValueError,match='title'):publisher.edit(pid,'  ','')


@pytest.mark.parametrize('status',['failed','rejected','deleted',None])
def test_failed_remote_upload_status_cannot_be_reported_as_published(ready,status):
    jid,_,_=ready
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','')
    class YouTube:
        def request(self,*a,**kw):
            return httpx.Response(200,json={'items':[{'snippet':{'channelId':'channel-fixture'},'status':{'privacyStatus':'private','uploadStatus':status}}]})
    with pytest.raises(publisher.Uncertain,match='upload status'):
        publisher.complete(pid,{'id':'youtube-fixture'},publisher.history()[0]['metadata'],YouTube(),'channel-fixture')
    assert publisher.history()[0]['video_id']=='youtube-fixture'


def test_quota_diagnostic_is_actionable_and_never_exposes_raw_response():
    response=httpx.Response(403,json={'error':{'message':'private session URL must not escape','errors':[{'reason':'quotaExceeded'}]}})
    error=publisher.upload_error(response,'YouTube upload')
    assert 'quota is exhausted' in str(error) and 'HTTP 403' in str(error)
    assert 'private session' not in str(error)


def test_explicit_source_credit_survives_queue_creation_and_edits(ready):
    jid,_,_=ready
    credit='Credit: NASA. Informational software verification; no endorsement.'
    with store.connect() as db:
        request=json.loads(db.execute('SELECT request FROM jobs WHERE id=?',(jid,)).fetchone()['request'])
        request['source_attribution']=credit
        db.execute('UPDATE jobs SET request=? WHERE id=?',(json.dumps(request),jid))
    with pytest.raises(ValueError,match='UTF-8 bytes'):
        publisher.enqueue(jid,0,'channel-fixture','Title','x'*4990)
    pid=publisher.enqueue(jid,0,'channel-fixture','Title','Description about the source.')
    description=publisher.history()[0]['metadata']['snippet']['description']
    assert description.endswith(credit) and len(description)<=5000
    publisher.edit(pid,'Edited','Changed description')
    assert publisher.history()[0]['metadata']['snippet']['description'].endswith(credit)
    publisher.edit(pid,'Edited',credit)
    assert publisher.history()[0]['metadata']['snippet']['description']==credit


def test_multilingual_metadata_enforces_youtube_byte_limit_before_upload(ready):
    jid,_,_=ready
    with pytest.raises(ValueError,match='UTF-8 bytes'):
        publisher.enqueue(jid,0,'channel-fixture','Український заголовок','Ї'*3000)
    with pytest.raises(ValueError,match='without'):
        publisher.enqueue(jid,0,'channel-fixture','<Invalid title>','')
    with pytest.raises(ValueError,match='HTML'):
        publisher.enqueue(jid,0,'channel-fixture','Title','<b>Invalid description</b>')
    assert publisher.history()==[]
