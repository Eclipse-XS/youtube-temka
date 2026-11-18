import json
from pathlib import Path
import shutil
import pytest
from factory import config, media, store
from factory.models import JobRequest


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'db.sqlite3')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)
    monkeypatch.setenv('FFMPEG_ENCODER','x264')
    config.initialize()
    # Real generated H.264/AAC fixture, with a changing test pattern and tone.
    source=config.SCRATCH/'uploads'/'fixture.mp4'
    source.parent.mkdir()
    media.run([media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','6','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)])
    words=[{'word':' '+w,'start':i*.4,'end':(i+1)*.4} for i,w in enumerate('Hello Україна русский español synchronized caption test with a natural ending'.split())]
    transcript={'language':'en','segments':[{'start':0,'end':5,'text':'Hello Україна русский español synchronized caption test with a natural ending','words':words}]}
    return source,transcript,tmp_path


@pytest.mark.parametrize('preset',['crop','blur','gameplay'])
def test_real_vertical_render_with_multilingual_captions(fixture,preset):
    import av
    source,transcript,tmp_path=fixture
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,preset=preset)
    output=tmp_path/(preset+'.mp4')
    background=source
    if preset=='gameplay':
        background=tmp_path/'one-second-background.mp4'
        media.run([media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-i',str(source),'-t','1','-an','-c:v','copy',str(background)])
    media.render(source,output,transcript,0,5,req,background)
    media.validate_output(output,5)
    with av.open(str(output)) as container:
        assert (container.streams.video[0].width,container.streams.video[0].height)==(1080,1920)
        assert len(container.streams.audio)==1
    assert 'Україна' in output.with_suffix('.ass').read_text(encoding='utf-8')


def test_real_longs_concatenation_and_order(fixture):
    import av
    source,transcript,tmp_path=fixture
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,mode='longs',resolution=720)
    paths=[]
    for i in range(2):
        cut=tmp_path/f'cut-{i}.mp4'
        media.download('upload:fixture.mp4',cut,i*2,(i+1)*2,720)
        output=tmp_path/f'part-{i}.mp4'
        media.render(cut,output,transcript,i*2,(i+1)*2,req)
        paths.append(output)
    final=tmp_path/'long.mp4'
    media.concatenate(paths,final)
    media.validate_output(final,4)
    with av.open(str(final)) as container:
        assert (container.streams.video[0].width,container.streams.video[0].height)==(1280,720)


def test_opening_text_hook_is_really_rendered(fixture):
    source,transcript,tmp_path=fixture
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,hook='A clear opening hook')
    output=tmp_path/'with-hook.mp4'
    media.render(source,output,transcript,0,5,req)
    media.validate_output(output,5)
    assert output.with_suffix('.hook.txt').read_text(encoding='utf-8')=='A clear opening hook'


def test_pipeline_local_manual_clip_is_playable_without_drive(fixture,monkeypatch):
    from factory.pipeline import process
    source,transcript,tmp_path=fixture
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,intervals=[(0,5)])
    job=store.create(req.model_dump())
    root=config.SCRATCH/job['id']
    root.mkdir()
    # Seed a known transcript checkpoint: this test verifies assembly, not ASR.
    (root/'transcript.json').write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
    process(store.claim('fixture-worker'))
    complete=store.get(job['id'])
    assert complete['state']=='READY',complete['error']
    media.validate_output(root/'clip-1.mp4',5)
    assert (root/'transcript.vtt').read_text(encoding='utf-8').startswith('WEBVTT')
    assert (root/'transcript.json').is_file()


def test_two_hour_fixture_extracts_only_selected_absolute_interval(fixture):
    import av
    _,_,tmp_path=fixture
    long_source=config.SCRATCH/'uploads'/'long-fixture.mp4'
    media.run([media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=1','-t','7300','-c:v','libx264','-preset','ultrafast','-crf','35',str(long_source)])
    metadata=media.probe('upload:long-fixture.mp4')
    assert metadata['duration']>7200
    selected=tmp_path/'selected-after-two-hours.mp4'
    media.download('upload:long-fixture.mp4',selected,7201,7206,480)
    media.validate_output(selected,5)
    assert selected.stat().st_size<long_source.stat().st_size/20


@pytest.mark.parametrize('audio_mode',['silent','music'])
def test_audio_modes_create_real_expected_tracks(fixture,audio_mode):
    import av
    source,transcript,tmp_path=fixture
    music=config.DATA/'music';music.mkdir();(music/'licensed.mp4').write_bytes(source.read_bytes())
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,preset='crop',audio_mode=audio_mode,music_asset='licensed.mp4' if audio_mode=='music' else None)
    output=tmp_path/(audio_mode+'.mp4');media.render(source,output,transcript,0,5,req)
    with av.open(str(output)) as container:assert bool(container.streams.audio)==(audio_mode=='music')


def test_pause_removal_really_trims_video_audio_and_captions(fixture):
    source,_,tmp_path=fixture
    transcript={'language':'en','segments':[{'start':0,'end':5,'text':' First last','words':[{'word':' First','start':.3,'end':.6},{'word':' last','start':4.3,'end':4.7}]}]}
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,end=6,silence_removal=True,preset='crop')
    output=tmp_path/'without-pauses.mp4';media.render(source,output,transcript,0,5,req)
    report=json.loads(output.with_suffix('.validation.json').read_text(encoding='utf-8'))
    assert report['audio'] and 1<report['duration']<2
    srt=output.with_suffix('.srt').read_text(encoding='utf-8')
    assert 'last' in srt and '00:00:04' not in srt


def test_smart_camera_path_is_accepted_by_real_ffmpeg(fixture,monkeypatch):
    from factory import framing
    source,transcript,tmp_path=fixture
    monkeypatch.setattr(framing,'trajectory',lambda *_:((202,358,[0,30,60,90,120,150,180,210,240,270]),{'strategy':'face_tracking','detector_fixture':True}))
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,end=6,preset='smart')
    output=tmp_path/'tracking.mp4';media.render(source,output,transcript,0,5,req)
    assert output.with_suffix('.camera.txt').is_file()
    media.validate_output(output,5,request=req)


def test_corrupted_output_cannot_be_accepted(tmp_path):
    broken=tmp_path/'broken.mp4';broken.write_bytes(b'not an MP4 container')
    with pytest.raises(Exception):media.validate_output(broken,5)


def test_pipeline_reuses_frozen_highlights_after_interruption(fixture,monkeypatch):
    from factory import pipeline
    _,transcript,_=fixture
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,minimum=5,maximum=6,end=6,preset='crop')
    job=store.create(req.model_dump());root=config.SCRATCH/job['id'];root.mkdir()
    (root/'transcript.json').write_text(json.dumps(transcript),encoding='utf-8')
    (root/'analysis.json').write_text(json.dumps({'analysis':'ollama','candidates':[{'start_seconds':0,'end_seconds':5,'title':'Frozen selection'}]}),encoding='utf-8')
    monkeypatch.setattr(pipeline,'analyze',lambda *_:(_ for _ in ()).throw(AssertionError('A retry must not rerank existing clip identities')))
    pipeline.process(store.claim('resumed-worker'))
    result=store.get(job['id'])
    assert result['state']=='READY',result['error']
    assert result['result']['outputs'][0]['title']=='Frozen selection'


def test_pipeline_renders_synchronized_background_and_music_without_local_library(fixture):
    import hashlib
    import httpx
    from factory import assets,pipeline
    source,transcript,_=fixture
    payload=source.read_bytes()
    digest=hashlib.sha256(payload).hexdigest()
    manifest=[{'kind':kind,'name':'approved.mp4','size':len(payload),'sha256':digest} for kind in ('backgrounds','music')]
    with httpx.Client(base_url='http://controller',transport=httpx.MockTransport(lambda _:httpx.Response(200,content=payload))) as client:
        paths=assets.sync(client,manifest)
    assert set(paths)=={'backgrounds','music'}
    assert not (config.DATA/'backgrounds').exists() and not (config.DATA/'music').exists()
    req=JobRequest(source='upload:fixture.mp4',rights_confirmed=True,save_drive=False,end=6,minimum=5,maximum=6,intervals=[(0,5)],preset='gameplay',audio_mode='music',music_asset='approved.mp4')
    job=store.create(req.model_dump());root=config.SCRATCH/job['id'];root.mkdir()
    (root/'transcript.json').write_text(json.dumps(transcript),encoding='utf-8')
    pipeline.process(store.claim('remote-assets-test'),assets=paths)
    complete=store.get(job['id'])
    assert complete['state']=='READY',complete['error']
    report=complete['result']['outputs'][0]['validation']
    assert report['audio'] and (report['width'],report['height'])==(1080,1920)
