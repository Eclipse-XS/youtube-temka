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
