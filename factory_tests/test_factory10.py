import json

import httpx
import pytest

from factory import config, media, pipeline, store
from factory.api import preflight_job
from factory.inference import ModelBudgetExceeded, generate
from factory.models import JobRequest
from factory.progress import MODEL_PROGRESS, Progress
from factory.visual_review import VisualReview


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'jobs.db')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)
    monkeypatch.setenv('FFMPEG_ENCODER','x264')
    return tmp_path


def test_operations_preserve_source_and_lease_history(workspace):
    job=store.create({'source':'upload:owned.mp4'})
    claim=store.claim('first')
    first=Progress(lambda state=None,**kwargs:store.update(job['id'],claim['lease'],state,**kwargs))
    first.source_id='source-1'
    first.begin('signals','ANALYZING',2,'windows')
    first.done()
    first.source_id='source-2'
    first.begin('signals','ANALYZING',4,'windows')
    store.cancel(job['id'])
    assert store.retry(job['id'])
    claim=store.claim('second')
    second=Progress(lambda state=None,**kwargs:store.update(job['id'],claim['lease'],state,**kwargs))
    second.source_id='source-2'
    second.begin('signals','ANALYZING',4,'windows')
    second.done()
    operations=store.operations(job['id'])
    assert [(op['source_id'],op['attempt'],op['status']) for op in operations]==[
        ('source-2',2,'completed'),('source-2',1,'cancelled'),('source-1',1,'completed')]
    assert all(op['elapsed_seconds']>=0 for op in operations)
    assert operations[0]['processed_units']==4


def test_streamed_model_metrics_and_retry_budget_are_durable(workspace,monkeypatch):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','0')
    job=store.create({'source':'upload:owned.mp4'})
    claim=store.claim('model-worker')
    progress=Progress(lambda state=None,**kwargs:store.update(job['id'],claim['lease'],state,**kwargs))
    request=JobRequest(source='upload:owned.mp4',rights_confirmed=True,max_text_model_calls=1)
    progress.limit_models(request,claim['model_usage'])
    progress.begin('highlights','ANALYZING')

    def mock_ollama(request):
        if request.method=='GET':
            return httpx.Response(200,json={'models':[{'name':'fixture','size':20,'size_vram':10,'digest':'digest'}]})
        assert json.loads(request.content)['stream'] is True
        messages=[{'response':'{"ok":','done':False},{'response':'true}','done':True,
                  'eval_count':4,'eval_duration':500_000_000,'prompt_eval_count':20,'load_duration':10_000_000}]
        return httpx.Response(200,headers={'content-type':'application/x-ndjson'},
                              text='\n'.join(map(json.dumps,messages)))

    context=MODEL_PROGRESS.set(progress)
    try:
        with httpx.Client(transport=httpx.MockTransport(mock_ollama)) as client:
            call={'model':'fixture','options':{'num_ctx':2048,'num_predict':80}}
            response=generate(client,'http://model.invalid/api/generate',call)
            assert json.loads(response.json()['response'])=={'ok':True}
            with pytest.raises(ModelBudgetExceeded):
                generate(client,'http://model.invalid/api/generate',call)
    finally:
        MODEL_PROGRESS.reset(context)
    operations=store.operations(job['id'])
    assert operations[0]['error_code']=='MODEL_BUDGET_EXHAUSTED'
    measured=operations[1]['details']
    assert (measured['tokens_per_second'],measured['device'],measured['received_fragments'])==(8,'mixed',2)
    store.cancel(job['id'])
    assert store.retry(job['id'])
    assert store.claim('model-retry')['model_usage']['text']==1


def test_gameplay_processing_scans_every_window_and_skips_speech(workspace,monkeypatch):
    from factory import signals

    monkeypatch.setattr(signals,'WINDOW_SECONDS',1)
    config.initialize()
    path=config.SCRATCH/'uploads'/'generated.mp4'
    path.parent.mkdir(exist_ok=True)
    media.run([media.ffmpeg(),'-y','-hide_banner','-loglevel','error','-f','lavfi',
               '-i','testsrc2=s=320x180:r=12','-f','lavfi','-i','sine=frequency=420:sample_rate=16000',
               '-t','14','-c:v','libx264','-threads','2','-c:a','aac',str(path)])
    monkeypatch.setattr(pipeline,'transcribe_chunks',lambda *args,**kwargs: pytest.fail('unexpected ASR'))
    request=JobRequest(source='upload:generated.mp4',rights_confirmed=True,workflow='highlights',
                       ranking_profile='gameplay_only',gameplay_scan_fps=4,minimum=5,maximum=8,count=1,
                       captions=False,save_drive=False,max_text_model_calls=0,preset='crop')
    estimate=preflight_job(request)['estimate']
    assert estimate['signal_windows']==14 and estimate['audio_seconds_upper_bound']==0
    job=store.create(request.model_dump())
    pipeline.process(store.claim('fixture'))
    done=store.get(job['id'])
    assert done['state']=='READY',done['error']
    coverage=done['result']['signal_coverage']
    assert coverage['full_range'] and coverage['windows']==14 and coverage['fps']==4
    assert coverage['frames_sampled']>=52
    assert done['result']['outputs'][0]['validation']['audio']
    event=done['result']['candidates'][0]
    assert event['category']=='unknown_event' and event['editorial_review_required']


def test_visual_review_cannot_point_to_an_unseen_or_earlier_payoff():
    decision={'category':'unexpected_collision','observation':'Two cars touch','setup':'Two cars approach',
              'trigger_frame':2,'payoff_frame':3,'evidence_frames':[1,2,3],
              'comprehensible_without_speech':True,'uncertain':False}
    assert VisualReview.model_validate(decision).payoff_frame==3
    with pytest.raises(ValueError,match='payoff'):
        VisualReview.model_validate({**decision,'payoff_frame':1})
    with pytest.raises(ValueError,match='payoff'):
        VisualReview.model_validate({**decision,'evidence_frames':[1,2]})


def test_caption_looks_and_retained_word_timings_are_independent(workspace):
    from factory.captions import appearance
    from subtitles import generate_ass

    transcript={'language':'uk','segments':[{'start':10,'end':12,'text':'Привіт світ',
                'words':[{'word':' Привіт','start':10,'end':11},{'word':' світ','start':11,'end':12}]}]}
    request=JobRequest(source='upload:owned.mp4',rights_confirmed=True,caption_style='one_word')
    origin={'id':'a'*32,'request':request.model_dump(),'result':{}}
    original=config.SCRATCH/origin['id']
    original.mkdir(parents=True)
    name=pipeline.save_edit_transcript(original,'edit-clip-1.json',transcript,10,12)
    edit=workspace/'edit'
    edit.mkdir()
    new=request.model_copy(update={'caption_style':'gaming_comic'})
    pipeline.reuse_edit_transcript(edit,origin,{'edit_transcript':name},new,lambda *_:None)
    retained=json.loads((edit/'transcript.json').read_text(encoding='utf-8'))
    assert [(word['start'],word['end']) for word in retained['segments'][0]['words']]==[(0,1),(1,2)]
    for style,file in [(request,'one.ass'),(new,'comic.ass')]:
        assert generate_ass(retained,0,2,edit/file,**appearance(style))
    one=(edit/'one.ass').read_text(encoding='utf-8-sig')
    comic=(edit/'comic.ass').read_text(encoding='utf-8-sig')
    assert one!=comic and 'ПРИВІТ' in one and 'ПРИВІТ' in comic
