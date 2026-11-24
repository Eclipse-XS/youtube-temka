import json
import threading
import httpx
import pytest
from factory.models import JobRequest
from factory.highlights import analyze
from factory.audio_edit import speech_timeline
from factory import config,store


def req(**kw):return JobRequest(source='upload:test.mp4',rights_confirmed=True,save_drive=False,**kw)


@pytest.mark.parametrize('decision',['unsuitable','visual_required'])
def test_explicit_suitability_decision_is_not_replaced_by_heuristics(monkeypatch,decision):
    def respond(*a,**kw):return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'response':json.dumps({'candidates':[],'decision':decision,'explanation':'No standalone context in this excerpt'})})
    monkeypatch.setattr(httpx.Client,'post',respond)
    result=analyze({'language':'en','segments':[{'start':0,'end':25,'text':'This sentence has enough actual words to make a deterministic heuristic candidate but context is still missing here.'}]},req(),25)
    assert result['analysis']=='ollama' and result['candidates']==[]
    assert result['analysis_diagnostics']['requests']==1


def test_empty_unexplained_ranking_retries_and_produces_reviewable_fallback(monkeypatch):
    def respond(*a,**kw):return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'response':'{"candidates":[]}'})
    monkeypatch.setattr(httpx.Client,'post',respond)
    result=analyze({'language':'en','segments':[{'start':0,'end':25,'text':'This sentence has enough actual words to make a deterministic heuristic candidate with context and a natural ending.'}]},req(),25)
    assert result['analysis_outcome']=='empty_llm_result' and result['candidates']
    assert result['analysis_diagnostics']['requests']==2


def test_malformed_window_does_not_skip_semantic_analysis_of_later_speech(monkeypatch):
    calls=[]
    def respond(*a,**kw):
        if 'prompt' not in kw['json']:
            return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'done':True})
        calls.append(kw['json'])
        candidate={'start_seconds':30,'end_seconds':55,'score':90,'title':'Later complete thought','language':'en','reason':'fixture','confidence':.8}
        result={'candidates':[]} if len(calls)<=2 else {'candidates':[candidate]}
        return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'response':json.dumps(result)})
    monkeypatch.setattr(httpx.Client,'post',respond)
    transcript={'language':'en','segments':[{'start':0,'end':25,'text':'word '*720+'.'},{'start':30,'end':55,'text':'A later self contained thought has enough words to be considered independently and ends naturally.'}]}
    result=analyze(transcript,req(),60)
    assert len(calls)==3 and result['analysis_diagnostics']['windows']==2
    later=next(c for c in result['candidates'] if c['start_seconds']==30)
    assert later['selection_method']=='ollama' and later['analysis_model']
    assert result['analysis']=='heuristic'  # The mixed fallback remains visible.


def test_invented_title_is_replaced_with_source_quote_and_requires_review(monkeypatch):
    def respond(*a,**kw):
        candidate={'start_seconds':0,'end_seconds':25,'score':9,'title':"Leo's Vision for the Space Station",'language':'en','reason':'fixture','confidence':1}
        return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'response':json.dumps({'candidates':[candidate]})})
    monkeypatch.setattr(httpx.Client,'post',respond)
    text='The space station has been the cornerstone of low Earth orbit for over two decades and continues to support important research.'
    result=analyze({'language':'en','segments':[{'start':0,'end':25,'text':text}]},req(),25)
    candidate=result['candidates'][0]
    assert candidate['editorial_review_required'] and candidate['title_method']=='transcript_quote'
    assert "Leo" not in candidate['title'] and text.startswith(candidate['title'])
    assert candidate['suggested_title']=="Leo's Vision for the Space Station"


def test_pause_removal_maps_words_and_video_to_same_timeline():
    transcript={'language':'en','segments':[{'start':10,'end':18,'text':' one two','words':[{'word':' one','start':10.5,'end':11},{'word':' two','start':17,'end':17.5}]}]}
    ranges,timed,start,end=speech_timeline(transcript,10,18)
    assert len(ranges)==2 and end<2
    assert start==0 and timed['segments'][1]['words'][0]['end']<=end
    assert transcript['segments'][0]['start']==10


def test_multi_hour_checkpoints_keep_absolute_offsets_once(tmp_path,monkeypatch):
    from factory.pipeline import transcribe_chunks
    from factory.progress import Progress
    root=tmp_path/'job';root.mkdir()
    for offset in range(0,10800,900):
        (root/f'transcript-{offset}.json').write_text(json.dumps({'language':'en','segments':[{'start':1,'end':26,'text':'An actual checkpoint sentence.','words':[{'word':' sentence','start':2,'end':3}]}]}),encoding='utf-8')
    updates=[]
    progress=Progress(lambda *args,**kwargs:updates.append(kwargs))
    result=transcribe_chunks('never-fetched',req(end=None),root,{},10800,720,progress,lambda **kw:updates.append(kw))
    assert len(result['segments'])==12 and result['segments'][-1]['start']==9901
    assert result['segments'][-1]['words'][0]['start']==9902
    again=transcribe_chunks('never-fetched',req(end=None),root,{},10800,720,progress,lambda **kw:None)
    assert again==result


def test_worker_survives_first_job_and_processes_second(tmp_path,monkeypatch):
    from factory.worker import local_loop
    from factory import pipeline
    monkeypatch.setattr(config,'DATA',tmp_path);monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch');monkeypatch.setattr(config,'DB',tmp_path/'db')
    monkeypatch.setenv('WORKER_ID','two-job-test')
    for _ in range(2):store.create(req().model_dump())
    stop=threading.Event();done=[]
    def process(claim):
        done.append(claim['job']['id'])
        if len(done)==1:raise RuntimeError('Unexpected fault')
        store.update(claim['job']['id'],claim['lease'],state='READY')
        stop.set()
    monkeypatch.setattr(pipeline,'process',process)
    local_loop(stop)
    assert len(done)==2 and {j['state'] for j in store.list_jobs()}=={'FAILED','READY'}


def test_expired_processing_lease_requeues_and_fences_after_backoff(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path);monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch');monkeypatch.setattr(config,'DB',tmp_path/'db')
    job=store.create(req().model_dump());claim=store.claim('dead-worker')
    store.update(job['id'],claim['lease'],state='TRANSCRIBING',stage_update={'key':'transcription','status':'running','current':900,'total':1800,'unit':'seconds'})
    with store.connect() as db:db.execute('UPDATE jobs SET seen=0 WHERE id=?',(job['id'],))
    assert store.claim('replacement') is None
    recovering = store.get(job['id'])
    assert recovering['stages'][0]['current']==900
    assert recovering['state']=='QUEUED'
    assert recovering['result']['failure']['code']=='WORKER_LEASE_EXPIRED'
    monkeypatch.setattr(store.time,'time',lambda:recovering['result']['retry_at']+1)
    fresh=store.claim('replacement')
    with pytest.raises(InterruptedError):store.update(job['id'],claim['lease'],state='READY')
    assert fresh['lease']!=claim['lease']


def test_transient_stage_retries_are_persisted_and_bounded(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'db')
    now = 100
    monkeypatch.setattr(store.time,'time',lambda:now)
    job=store.create(req().model_dump())
    failure={'code':'DOWNLOAD_RATE_LIMITED','stage':'retrieval','message':'rate limited','retryable':True}
    for expected in ('QUEUED','QUEUED','FAILED'):
        claim=store.claim('worker')
        store.update(job['id'],claim['lease'],state='QUEUED',result={'failure':failure})
        recovering=store.get(job['id'])
        assert recovering['state']==expected
        assert store.claim('worker') is None
        now = recovering['result'].get('retry_at',now)+1
    assert recovering['result']['failure']['attempt']==3
