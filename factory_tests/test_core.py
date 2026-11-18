import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from factory import config, store
from factory.models import JobRequest, Candidate
from factory.highlights import select, analyze
from factory.resources import preflight


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'jobs.sqlite3')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)


def request(**kw):
    return JobRequest(source='upload:test.mp4',rights_confirmed=True,save_drive=False,**kw)


def test_claim_is_atomic_and_stale_worker_cannot_write():
    job=store.create(request().model_dump())
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims=list(pool.map(lambda i:store.claim(str(i)),range(8)))
    assert sum(c is not None for c in claims)==1
    claim=next(c for c in claims if c)
    store.cancel(job['id'])
    with pytest.raises(InterruptedError):
        store.update(job['id'],claim['lease'],state='READY')
    assert store.retry(job['id'])
    next_claim=store.claim('new')
    with pytest.raises(InterruptedError):
        store.update(job['id'],claim['lease'],state='READY')
    store.update(job['id'],next_claim['lease'],state='READY',result={'outputs':[]})
    assert store.get(job['id'])['state']=='READY'


def test_expired_upload_is_blocked_and_never_automatically_replayed():
    job=store.create(request().model_dump())
    claim=store.claim('old')
    store.update(job['id'],claim['lease'],state='UPLOADING')
    with store.connect() as db:
        db.execute('UPDATE jobs SET seen=0 WHERE id=?',(job['id'],))
    assert store.claim('new') is None
    assert store.get(job['id'])['state']=='BLOCKED'


def test_queue_persists_across_connections():
    job=store.create(request().model_dump())
    claim=store.claim('worker-a')
    store.update(job['id'],claim['lease'],result={'language':'uk'},current=30,total=60)
    assert store.get(job['id'])['result']['language']=='uk'
    assert store.get(job['id'])['current']==30


def test_remote_worker_does_not_claim_local_sources():
    store.create(request().model_dump())
    assert store.claim('remote',remote=True) is None


def test_one_active_claim_per_worker():
    store.create(request().model_dump())
    store.create(request().model_dump())
    assert store.claim('same-pc') is not None
    assert store.claim('same-pc') is None
    assert store.claim('second-pc') is not None


def test_disk_reserve_and_budget_fail_closed(monkeypatch):
    config.initialize()
    (config.SCRATCH/'large').write_bytes(b'12345')
    monkeypatch.setattr(config,'SCRATCH_BYTES',4)
    with pytest.raises(RuntimeError,match='budget'):
        preflight()
    monkeypatch.setattr(config,'SCRATCH_BYTES',100)
    monkeypatch.setattr(config,'RESERVE_BYTES',10**20)
    with pytest.raises(RuntimeError,match='reserve'):
        preflight()


def test_candidate_selection_is_valid_deduplicated_deterministic():
    def c(a,b,score):
        return Candidate(start_seconds=a,end_seconds=b,score=score,title='Тест',language='uk',reason='fixture',confidence=.7)
    candidates=[c(0,30,80),c(1,31,90),c(45,75,85),c(80,150,99)]
    result=select(candidates,request(),100)
    assert [c['start_seconds'] for c in result]==[1,45]
    assert select(list(reversed(candidates)),request(),100)==result


def test_ollama_unavailable_returns_explicit_heuristics(monkeypatch):
    import httpx
    def fail(*_,**__):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.Client,'post',fail)
    transcript={'language':'uk','segments':[{'start':0,'end':25,'text':'Це авторизований тестовий уривок для перевірки роботи алгоритму пошуку моментів і правильного завершення речення.'}]}
    result=analyze(transcript,request(),25)
    assert result['analysis']=='heuristic'
    assert result['model'] is None
    assert result['candidates'][0]['language']=='uk'


def test_semantically_invalid_llm_intervals_retry_then_fall_back(monkeypatch):
    import httpx
    calls=[]
    def respond(*_,**__):
        calls.append(1)
        invalid={'start_seconds':0,'end_seconds':5,'score':90,'title':'Invalid too-short interval','language':'en','reason':'fixture','confidence':.9}
        return httpx.Response(200,request=httpx.Request('POST','http://fixture.invalid'),json={'response':json.dumps({'candidates':[invalid]})})
    monkeypatch.setattr(httpx.Client,'post',respond)
    transcript={'language':'en','segments':[{'start':0,'end':25,'text':'This authorized test contains enough clearly spoken words to provide a complete short highlight with a natural ending.'}]}
    result=analyze(transcript,request(),25)
    assert len(calls)==2
    assert result['analysis']=='heuristic'
    assert result['candidates'][0]['end_seconds']==25
    assert result['analysis_diagnostics']['rejected_intervals']==2


def test_validation_rejects_unsafe_ranges_and_missing_rights():
    for kw in ({'end':0},{'start':100,'end':50},{'end':86401},{'intervals':[(0,float('nan'))]}):
        with pytest.raises(ValueError):
            request(**kw)
    with pytest.raises(ValueError):
        JobRequest(source='x',rights_confirmed=False)


def test_verified_cloud_checkpoint_recovers_without_original_source():
    from factory.pipeline import process
    job=store.create(request().model_dump())
    claim=store.claim('first')
    store.update(job['id'],claim['lease'],state='BLOCKED',result={'cloud_verified':True,'outputs':[]})
    assert store.retry(job['id'])
    process(store.claim('restart'))
    assert store.get(job['id'])['state']=='READY'


def test_first_start_creates_data_directory_with_independent_scratch(tmp_path,monkeypatch):
    data=tmp_path/'new-data'
    monkeypatch.setattr(config,'DATA',data)
    monkeypatch.setattr(config,'DB',data/'jobs.sqlite3')
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'separate-scratch')
    job=store.create(request().model_dump())
    assert store.get(job['id'])['state']=='QUEUED'
    assert data.is_dir() and config.SCRATCH.is_dir()


def test_heuristic_waits_for_complete_sentence_within_duration_bounds():
    from factory.highlights import heuristics
    transcript={'language':'uk','segments':[
        {'start':0,'end':20,'text':'Це достатньо довгий початок важливої думки який містить понад дванадцять слів але ще не завершений'},
        {'start':20.1,'end':26,'text':'і ось її логічне завершення.'},
        {'start':28,'end':50,'text':'Наступна незалежна думка має інший зміст і достатньо слів для окремого уривка.'}]}
    candidates=heuristics(transcript,request())
    assert candidates[0].start_seconds==0 and candidates[0].end_seconds==26
    assert all(c.end_seconds-c.start_seconds<=60 for c in candidates)
