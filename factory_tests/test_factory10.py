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

    monkeypatch.setattr(signals,'scan',lambda *args,**kwargs:pytest.fail('unexpected rescan'))
    again=store.create(request.model_dump())
    pipeline.process(store.claim('fixture'))
    repeated=store.get(again['id'])
    assert repeated['state']=='READY',repeated['error']
    assert set(repeated['result']['cache_hits']) >= {'source_metadata','visual_signals','candidate_discovery',
                                                    'selected_media','scene_render'}
    assert repeated['result']['outputs'][0]['output_hash']==done['result']['outputs'][0]['output_hash']


def test_visual_review_cannot_point_to_an_unseen_or_earlier_payoff():
    decision={'category':'unexpected_collision','observation':'Two cars touch','setup':'Two cars approach',
              'trigger_frame':2,'payoff_frame':3,'evidence_frames':[1,2,3],
              'comprehensible_without_speech':True,'uncertain':False}
    assert VisualReview.model_validate(decision).payoff_frame==3
    with pytest.raises(ValueError,match='payoff'):
        VisualReview.model_validate({**decision,'payoff_frame':1})
    with pytest.raises(ValueError,match='payoff'):
        VisualReview.model_validate({**decision,'evidence_frames':[1,2]})


def test_gameplay_keeps_local_motion_separate_from_motion_peaks():
    from factory.signals import gameplay_candidates, gameplay_proposal_limit

    request = JobRequest(source='upload:owned.mp4', rights_confirmed=True, workflow='highlights',
                         ranking_profile='gameplay_only', minimum=5, maximum=8, count=1)
    events = [(4, .010, 0, .19), (4.5, .009, 0, .15), (24, .12, 0, .31), (25, .06, 0, .25)]
    proposals = gameplay_candidates(events, [], request, 40, 'Gameplay', {'fps': 2}, 'source-1',
                                    gameplay_proposal_limit(request))
    assert len(proposals) == 2
    assert {item['proposal_kind'] for item in proposals} == {'local_motion', 'motion'}
    localized = next(item for item in proposals if item['proposal_kind'] == 'local_motion')
    assert localized['evidence']['motion'] < .025 and localized['semantic_score'] is None
    assert localized['editorial_review_required']


def test_gameplay_proposals_trim_black_lead_in_without_losing_the_event():
    from factory.signals import gameplay_candidates

    request = JobRequest(source='upload:owned.mp4', rights_confirmed=True, workflow='highlights',
                         ranking_profile='gameplay_only', minimum=5, maximum=8, count=1)
    events = [(4, .16, 0, .31), (6, .12, 0, .28), (7, .06, 0, .15)]
    coverage = {'fps': 2, 'black_intervals': [[0, 5]]}
    proposal, = gameplay_candidates(events, [], request, 20, 'Gameplay', coverage, 'source-1', 1)
    assert proposal['event_seconds'] == 6
    assert (proposal['start_seconds'], proposal['end_seconds']) == (5, 13)


def test_gameplay_visual_budget_reviews_each_source_before_expansion(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from factory import visual_review
    from factory.progress import Progress

    request = JobRequest(source='upload:owned.mp4', rights_confirmed=True, workflow='highlights',
                         ranking_profile='gameplay_only', visual_model='test', max_visual_model_calls=3)
    progress = Progress(lambda *args, **kwargs: None)
    progress.limit_models(request, {})
    calls = []

    def generate(client, url, payload, session):
        import httpx
        calls.append((progress.source_id, len(payload['images']), payload['options']['num_ctx']))
        assert progress.reserve_model('visual', payload['options']['num_ctx'], 400)
        last = len(payload['images'])
        review = {'category': 'unknown_event' if last == 3 else 'physics_glitch', 'observation': 'A wheel floats',
                  'setup': 'A parked car', 'trigger_frame': 2, 'payoff_frame': last,
                  'evidence_frames': [1, 2, last], 'comprehensible_without_speech': True, 'uncertain': last == 3}
        return httpx.Response(200, json={'response': json.dumps(review)})

    monkeypatch.setattr(visual_review, 'generate', generate)
    monkeypatch.setattr(visual_review, 'model_session', lambda *args: nullcontext({'layers': 0}))
    monkeypatch.setattr(visual_review, 'frame_images', lambda source, times, *args: ['image'] * len(times))

    def candidate(source, score):
        return {'source_id': source, 'source_frame_times': [1, 3, 5], 'start_seconds': 0, 'end_seconds': 9,
                'heuristic_score': score, 'proposal_kind': 'motion', 'evidence': {'score_components': {}}}

    first = candidate('source-1', 30)
    second = candidate('source-2', 5)
    visual_review.review_candidates([([first, candidate('source-1', 20)], 'upload:one.mp4', 480, tmp_path),
                                    ([second], 'upload:two.mp4', 480, tmp_path)], request, progress)
    assert calls[:2] == [('source-1', 3, 4096), ('source-2', 3, 4096)]
    assert calls[2] == ('source-1', 6, 8192)
    assert first['payoff_seconds'] == first['source_frame_times'][-1]
    assert second['visual_review_state'] == 'uncertain'


def test_gameplay_plan_links_sources_and_leaves_unsupported_beats_empty():
    from factory.compilation import plan_gameplay
    from factory.models import CompilationSource

    def clip(source, start, score, category):
        return {'source_id':source,'start_seconds':start,'end_seconds':start+10,'score':score,
                'event_seconds':start+3,'source_frame_times':[start+1,start+3,start+6],
                'visual_review':{'uncertain':False,'category':category,'setup':'A vehicle approaches',
                                 'observation':'The vehicle stalls','trigger_frame':2,'payoff_frame':3}}

    primary='source-1'
    additional='source-2'
    prefs={primary:CompilationSource(source='upload:a.mp4',max_contribution=20),
           additional:CompilationSource(source='upload:b.mp4',event_categories=['vehicle_crash'])}
    groups=[[clip(primary,0,40,'stunt_fail'),clip(primary,11,31,'stunt_fail')],
            [clip(additional,0,33,'vehicle_crash'),clip(additional,15,60,'physics_glitch')]]
    chosen,duration,plan=plan_gameplay(groups,3,30,prefs)
    assert duration==30 and [candidate['source_id'] for candidate in chosen]==[primary,additional,primary]
    assert plan['scenes'][0]['role']=='cold_open' and plan['scenes'][-1]['role']=='closing_scene'
    assert len(plan['chapters'])==1 and plan['chapters'][0]['theme']=='vehicles'
    assert {beat['type'] for beat in plan['scenes'][0]['event']['beats']}=={'setup','trigger','payoff'}
    assert plan['scenes'][0]['event']['editorial_uncertainty']=='model_hypothesis'
    scarce=[{'source_id':primary,'start_seconds':0,'end_seconds':10,'score':1,'event_seconds':3}]
    assert plan_gameplay([scarce],3,30,prefs)[:2]==([],0)


def test_gameplay_compilation_rejects_duplicate_recording_ranges_across_source_ids():
    from factory.compilation import plan_gameplay
    from factory.models import CompilationSource

    def candidate(source, start, score):
        return {'source_id': source, 'source_fingerprint': 'same-recording', 'start_seconds': start,
                'end_seconds': start + 10, 'event_seconds': start + 4, 'score': score}

    groups = [[candidate('source-1', 20, 50)], [candidate('source-2', 21, 49),
                                               candidate('source-2', 0, 30), candidate('source-2', 10, 24)]]
    prefs = {source: CompilationSource(source='upload:gameplay.mp4') for source in ('source-1', 'source-2')}
    chosen, seconds, _ = plan_gameplay(groups, 4, 40, prefs)
    assert seconds == 30
    assert [item['start_seconds'] for item in chosen] == [20, 0, 10]


def test_release_detection_counts_unique_events_and_reports_missing_payoff():
    from verification.factory10.acceptance_metrics import evaluate

    def clip(start, end):
        return {'source': 'gameplay', 'start': start, 'end': end}

    events = [{'source': 'gameplay', 'category': 'ragdoll', 'essential': [10, 12], 'trigger': 10,
               'payoff': [12, 13], 'low_motion_or_silent': True},
              {'source': 'gameplay', 'category': 'npc_behavior', 'essential': [20, 22], 'trigger': 20,
               'payoff': [24, 25], 'low_motion_or_silent': False}]
    metrics = evaluate([clip(9, 14), clip(9, 14), clip(19, 23)], events, [])
    assert metrics['precision_at_k'] == 1 / 3
    assert metrics['recall_at_k'] == metrics['payoff_preservation'] == .5
    assert metrics['low_motion_recall'] == 1


def test_gameplay_validation_enforces_100ms_stream_end_alignment(workspace):
    path = workspace / 'skew.mp4'
    media.run([media.ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
               '-i', 'color=blue:size=1280x720:duration=2', '-f', 'lavfi', '-i', 'sine=duration=1.8',
               '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac', str(path)])
    request = JobRequest(source='upload:owned.mp4', rights_confirmed=True, workflow='highlights',
                         mode='longs', ranking_profile='gameplay_only')
    assert media.validate_output(path, 2, expected_audio=True)['validated']
    with pytest.raises(RuntimeError, match='more than 100 ms'):
        media.validate_output(path, 2, request, expected_audio=True)


def test_gameplay_hooks_are_diverse_and_require_payoff_inside_scene():
    from factory.hooks import suggest_gameplay

    candidate={'start_seconds':0,'end_seconds':8,'source_offset':40,'source_frame_times':[42,44,46],
               'visual_review':{'category':'physics_glitch','observation':'The object moves through the floor',
                                'trigger_frame':2,'payoff_frame':3,'uncertain':False}}
    suggestions=suggest_gameplay(candidate,'uk')['candidates']
    assert len({option['style'] for option in suggestions})==len(suggestions)==3
    assert all('moves through the floor' in option['factual_support'] for option in suggestions)
    assert suggest_gameplay({**candidate,'end_seconds':5})['method']=='no_hook'
    assert suggest_gameplay({'category':'physics_glitch'})['candidates']==[]


def test_automatic_gameplay_edits_follow_visible_payoff_and_allow_explicit_removal():
    from factory.render_timeline import build, compile_scenes

    request=JobRequest(source='upload:owned.mp4',rights_confirmed=True,workflow='highlights',mode='longs',
                       ranking_profile='gameplay_only',editing_intensity='expressive',text_mode='static_hook')
    candidate={'start_seconds':0,'end_seconds':8,'source_frame_times':[1,2,4],
               'evidence':{'audio_onset':.01},
               'visual_review':{'category':'unexpected_collision','payoff_frame':3,'uncertain':False,
                                'action_focus':{'x':.6,'y':.2}}}
    scene=compile_scenes(build([candidate],request,{'source-1':8},1),request)[0]
    assert scene.effects[0].kind=='animated_zoom' and scene.effects[0].start==3.75
    assert scene.sounds[0].start==4 and scene.request.hook_position=='bottom'
    override={**candidate,'effects':[],'sounds':[]}
    scene=compile_scenes(build([override],request,{'source-1':8},2),request)[0]
    assert scene.effects==[] and scene.sounds==[]


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


def test_gameplay_vision_stops_after_equivalent_model_failures(tmp_path, monkeypatch):
    from contextlib import nullcontext
    import httpx
    from factory import visual_review
    from factory.progress import Progress

    request = JobRequest(source='upload:owned.mp4', rights_confirmed=True, ranking_profile='gameplay_only',
                         visual_model='test', max_visual_model_calls=4)
    progress = Progress(lambda *_args, **_kwargs: None)
    calls = []
    def generate(*args):
        calls.append(progress.source_id)
        raise httpx.ReadTimeout('vision stalled')
    monkeypatch.setattr(visual_review, 'generate', generate)
    monkeypatch.setattr(visual_review, 'model_session', lambda *args: nullcontext({'layers': None}))
    monkeypatch.setattr(visual_review, 'frame_images', lambda *_: ['frame'] * 3)
    candidates = [{'source_id': 'source-1', 'source_frame_times': [i,i+1,i+2],
                   'heuristic_score': 10-i, 'proposal_kind': 'motion'} for i in range(4)]
    visual_review.review_candidates([(candidates, request.source, 480, tmp_path)], request, progress)
    assert len(calls) == 2
    assert [item.get('visual_review_state') for item in candidates] == ['unavailable_or_invalid'] * 2 + [None] * 2
