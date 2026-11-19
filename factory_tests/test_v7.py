import json
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from factory import config,store,retention
from factory.models import JobRequest
from factory.timeline import connected,manifest
from factory.heavy import HostSlot


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'jobs.db')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)
    monkeypatch.setenv('FACTORY_HOST_LOCK_DIR',str(tmp_path/'locks'))
    config.initialize()
    return tmp_path


def test_host_slot_serializes_processes_and_is_reentrant(isolated):
    slot=HostSlot()
    script='from factory.heavy import HostSlot; s=HostSlot(); acquired=s.acquire(False); print(acquired); s.release() if acquired else None'
    with slot:
        with slot:
            assert subprocess.check_output([sys.executable,'-c',script],env=os.environ,text=True).strip()=='False'
    assert subprocess.check_output([sys.executable,'-c',script],env=os.environ,text=True).strip()=='True'


@pytest.mark.parametrize('overlap',[0,3,5])
def test_connected_series_uses_one_event_and_exact_overlap(overlap):
    req=JobRequest(source='upload:test.mp4',rights_confirmed=True,series_mode='connected',count=3,minimum=20,maximum=60,series_overlap=overlap)
    candidates=[{'start_seconds':10,'end_seconds':100,'title':'One continuous event','score':70},{'start_seconds':150,'end_seconds':175,'title':'Unrelated event','score':99}]
    parts,_=connected(candidates,req,180)
    assert len(parts)==3 and [p['part'] for p in parts]==[1,2,3]
    assert all(10<=p['start_seconds']<p['end_seconds']<=100 for p in parts)
    assert all(parts[i]['end_seconds']-parts[i+1]['start_seconds']==pytest.approx(overlap) for i in range(2))


def test_short_event_does_not_get_unrelated_filler():
    req=JobRequest(source='upload:test.mp4',rights_confirmed=True,series_mode='connected',count=3)
    parts,reason=connected([{'start_seconds':0,'end_seconds':25,'title':'Event'}],req,25)
    assert len(parts)==1 and '1/3' in reason


def test_manifest_preserves_operator_order_and_offsets():
    req=JobRequest(source='upload:test.mp4',rights_confirmed=True,mode='longs',start=100,end=200)
    value=manifest([{'start_seconds':50,'end_seconds':60},{'start_seconds':0,'end_seconds':20}],req)
    assert value['segments'][0]['source_start_ms']==150000
    assert value['segments'][1]['output_start_ms']==10000
    assert value['duration_ms']==30000


def packages(count):
    now=time.time()
    with store.connect() as db:
        for i in range(count):
            jid=f'{i+1:032x}'
            output={'drive':{'id':jid+'file','size':'1','md5Checksum':'hash'}}
            db.execute('INSERT INTO jobs(id,state,request,result,created) VALUES(?,?,?,?,?)',(jid,'READY',json.dumps({'source':'fixture'}),json.dumps({'cloud_verified':True,'outputs':[output]}),now-20*86400+i))
            db.execute('INSERT INTO retention_packages(job,files,created) VALUES(?,?,?)',(jid,json.dumps([output['drive']]),now-20*86400+i))
            db.execute('INSERT INTO publications(id,job,output,channel,state,metadata,video_id,created,seen) VALUES(?,?,?,?,?,?,?,?,?)',(jid,jid,0,'channel','PUBLISHED',json.dumps({'status':{'privacyStatus':'public'}}),'video',now-15*86400,now-15*86400))
        db.execute("INSERT INTO channels(id,alias,title) VALUES('channel','fixture','Fixture')")


@pytest.mark.parametrize('count,selected',[(49,0),(50,0),(51,1),(100,50)])
def test_retention_counts_packages_and_selects_oldest_first(isolated,count,selected):
    packages(count)
    result=retention.cleanup(dry_run=True)
    assert len(result['selected'])==selected
    assert result['selected']==[f'{i+1:032x}' for i in range(selected)]
    assert result['deleted']==[]


@pytest.mark.parametrize('state',['SCHEDULED','FAILED','UNCERTAIN','PUBLISHING'])
def test_retention_never_deletes_unverified_packages(isolated,state):
    packages(1)
    with store.connect() as db:db.execute('UPDATE publications SET state=?',(state,))
    assert not retention.candidates()[0]['eligible']


def test_retention_protects_active_edit_sources_and_enforces_grace(isolated):
    packages(1);jid=f'{1:032x}'
    retention.protect(jid,True)
    assert not retention.candidates()[0]['eligible']
    retention.protect(jid,False)
    store.create({'source':'edit:'+jid+':0'})
    assert 'active_reference' in retention.candidates()[0]['reasons']
    with store.connect() as db:
        db.execute("UPDATE jobs SET state='CANCELLED' WHERE state='QUEUED'")
        db.execute('UPDATE publications SET seen=?',(time.time(),))
    assert not retention.candidates()[0]['eligible']


def test_cleanup_failure_remains_retryable_and_blocks_new_edits(isolated,monkeypatch):
    packages(1);jid=f'{1:032x}'
    retention.configure({'enabled':True,'maximum_packages':50,'grace_days':7})
    monkeypatch.setattr(retention,'token_file',lambda _:None)
    class Response:
        def __init__(self,data):self.data=data
        def json(self):return self.data
    class Client:
        def __init__(self,*_):pass
        def close(self):pass
        def request(self,method,url,**kwargs):
            if url.endswith('/channels'):return Response({'items':[{'id':'channel'}]})
            if url.endswith('/videos'):return Response({'items':[{'snippet':{'channelId':'channel'},'status':{'privacyStatus':'public','uploadStatus':'processed'}}]})
            if method=='PATCH':raise OSError('offline')
            return Response({'size':'1','md5Checksum':'hash','appProperties':{'factoryKey':jid+'-clip.mp4'}})
    monkeypatch.setattr(retention,'Drive',Client)
    result=retention.cleanup(False)
    assert not result['deleted'] and len(result['errors'])==1
    assert retention.candidates()[0]['state']=='DELETION_PENDING'
    with pytest.raises(ValueError,match='expired'):store.create({'source':'edit:'+jid+':0'})


@pytest.mark.parametrize('language',['en','es','pt-BR','de','ru','uk'])
def test_neutral_hooks_are_localized_and_make_no_visual_claims(language):
    from factory.hooks import suggest,NEUTRAL
    result=suggest('',language)
    assert len(result['candidates'])==5 and result['review_required']
    assert all(h['text'] in NEUTRAL[language.split('-')[0]] for h in result['candidates'])


def test_starter_library_is_original_persistent_and_deduplicated(isolated):
    from factory.library import bootstrap,register
    assets=bootstrap()
    assert len(assets)==6 and len({item['sha256'] for item in assets})==6
    assert all(item['license']=='CC0-1.0' and item['fps']==24 and item['availability']=='AVAILABLE' for item in assets)
    path=isolated/'backgrounds'/'starter-bouncing-ball.mp4'
    duplicate=path.with_name('duplicate.mp4');duplicate.write_bytes(path.read_bytes())
    name,reused=register(duplicate,'backgrounds','CC0-1.0','fixture')
    assert reused and name==path.name and not duplicate.exists()
    assert len(bootstrap())==6


def test_translated_subtitles_preserve_phrase_times_and_render_without_fake_word_times(monkeypatch,tmp_path):
    import httpx
    from factory.captions import translate
    from subtitles import generate_ass
    calls=[]
    def respond(self,url,**kwargs):
        if 'prompt' not in kwargs['json']:return httpx.Response(200,request=httpx.Request('POST',url))
        calls.append(1)
        return httpx.Response(200,request=httpx.Request('POST',url),json={'response':json.dumps({'lines':[{'index':0,'text':'Привіт, Україно!'}]})})
    monkeypatch.setattr(httpx.Client,'post',respond)
    original={'language':'en','segments':[{'start':4,'end':7,'text':'Hello Ukraine','words':[{'word':' Hello','start':4,'end':5}]}]}
    translated=translate(original,'uk')
    assert translated['segments'][0]['start']==4 and translated['segments'][0]['end']==7
    assert translated['segments'][0]['words']==[] and original['segments'][0]['words']
    path=tmp_path/'captions.ass'
    generate_ass(translated,4,7,str(path))
    assert 'Привіт' in path.read_text(encoding='utf-8') and calls==[1]


def test_publication_rechecks_approval_before_any_network_call(isolated,monkeypatch):
    from factory import publisher
    job=store.create({'source':'fixture'})
    claim=store.claim('worker')
    store.update(job['id'],claim['lease'],state='READY',result={'cloud_verified':True,'outputs':[{'approved':True,'title':'Title','drive':{'id':'file'}}]})
    with store.connect() as db:db.execute("INSERT INTO channels(id,alias,title) VALUES('channel','alias','Title')")
    pid=publisher.enqueue(job['id'],0,'channel','Title','')
    publication=publisher.claim()
    store.approve(job['id'],0,False)
    monkeypatch.setattr(publisher,'Drive',lambda *_:pytest.fail('Revoked approval must prevent network work'))
    publisher.upload(publication)
    assert publisher.history()[0]['state']=='FAILED'


def test_approval_is_bound_to_the_render_version(isolated):
    from factory import publisher
    job=store.create({'source':'fixture'});claim=store.claim('worker')
    store.update(job['id'],claim['lease'],state='READY',result={'cloud_verified':True,'outputs':[{'render_id':'new','approved_render_id':'old','approved':True,'drive':{'id':'file'}}]})
    with pytest.raises(ValueError,match='different render'):publisher.enqueue(job['id'],0,'channel')


def test_channel_wall_time_rejects_dst_gaps_and_folds():
    from factory.calendar import local_time
    assert local_time('2026-11-19T12:00','Europe/Kyiv')=='2026-11-19T10:00:00+00:00'
    with pytest.raises(ValueError,match='ambiguous'):local_time('2026-10-25T03:30','Europe/Kyiv')
    with pytest.raises(ValueError,match='nonexistent'):local_time('2026-03-29T03:30','Europe/Kyiv')
    assert local_time('2026-10-25T03:30+03:00','Europe/Kyiv')=='2026-10-25T00:30:00+00:00'


def test_old_source_reference_is_not_lost_behind_ui_pagination(isolated):
    older=store.create({'source':'upload:shared.mp4'})
    with store.connect() as db:
        for i in range(205):
            db.execute('INSERT INTO jobs(id,state,request,created) VALUES(?,?,?,?)',(f'new-{i}','READY','{"source":"other"}',time.time()+i))
    assert older['id'] not in [job['id'] for job in store.list_jobs()]
    assert store.source_in_use('upload:shared.mp4','another-job')
    assert not store.source_in_use('upload:shared.mp4',older['id'])
