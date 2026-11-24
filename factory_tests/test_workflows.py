import json

import pytest

from factory import config, media, store
from factory.models import JobRequest
from factory.pipeline import process
from factory.timeline import story


def test_story_covers_twelve_minutes_and_prefers_nearby_boundary():
    request=JobRequest(source='upload:story.mp4',rights_confirmed=True,workflow='story',
                       destination='video',minimum=180,maximum=270,story_count=3,series_overlap=4)
    parts,_=story({'segments':[]},request,720,'Story',[243,480])
    assert parts[0]['start_seconds']==0
    assert parts[-1]['end_seconds']==720
    assert parts[0]['end_seconds']==243
    assert all(a['end_seconds']-b['start_seconds']==4 for a,b in zip(parts,parts[1:]))
    assert all(180<=p['end_seconds']-p['start_seconds']<=270 for p in parts)
    with pytest.raises(ValueError,match='YouTube Shorts'):
        JobRequest(**{**request.model_dump(),'destination':'youtube_shorts'})


@pytest.fixture
def owned_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'db')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)
    monkeypatch.setenv('FFMPEG_ENCODER','x264')
    uploads=config.SCRATCH/'uploads'
    uploads.mkdir(parents=True)
    inputs=[]
    for i,(size,rate) in enumerate([('160x90',24),('128x96',25),('128x128',30)]):
        name=f'fixture-{i}.mp4'
        args=[media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi',
              '-i',f'color=black:s={size}:r={rate}',
              '-vf',"drawbox=color=white:t=fill:enable='gte(t,3)'",
              '-t','6','-c:v','libx264','-threads','2',str(uploads/name)]
        media.run(args)
        inputs.append({'source':f'upload:{name}'})
    return inputs


def test_smart_highlights_renders_silent_visual_event(owned_sources):
    request=JobRequest(source=owned_sources[0]['source'],rights_confirmed=True,
                       workflow='highlights',minimum=5,maximum=6,count=1,
                       save_drive=False,audio_mode='silent',captions=False,preset='crop')
    job=store.create(request.model_dump())
    process(store.claim('fixture'))
    done=store.get(job['id'])
    assert done['state']=='READY',done['error']
    assert done['result']['candidates'][0]['selection_method']=='sampled_media_signals'
    assert done['result']['signal_coverage']['scanned_seconds']==6
    media.validate_output(config.SCRATCH/job['id']/'clip-1.mp4',5.5,request,expected_audio=False)


def test_compilation_reviews_and_renders_three_different_sources(owned_sources,monkeypatch):
    request=JobRequest(source=owned_sources[0]['source'],sources=owned_sources,
                       rights_confirmed=True,workflow='compilation',destination='video',
                       minimum=5,maximum=6,count=3,target_duration=16.5,save_drive=False,captions=False,
                       review_before_render=True)
    job=store.create(request.model_dump())
    assert store.claim('remote',remote=True) is None
    process(store.claim('fixture'))
    pending=store.get(job['id'])
    assert pending['state']=='REVIEW',pending['error']
    plan=pending['result']['edit_plan']
    segments=[{key:segment[key] for key in ('id','start_seconds','end_seconds','transition')}
              for segment in reversed(plan['segments'])]
    segments[0]['transition']='fade'
    saved=store.edit_plan(job['id'],plan['revision'],segments,16.5)
    with pytest.raises(InterruptedError):
        store.edit_plan(job['id'],plan['revision'],segments,None,approve=True)
    store.edit_plan(job['id'],saved['revision'],segments,None,approve=True)
    from factory import pipeline
    monkeypatch.setattr(pipeline,'transcribe_chunks',lambda *_:pytest.fail('Reran ASR after plan approval'))
    process(store.claim('fixture'))
    done=store.get(job['id'])
    assert done['state']=='READY',done['error']
    root=config.SCRATCH/job['id']
    assert [output['name'] for output in done['result']['outputs']]==['long.mp4']
    media.validate_output(root/'long.mp4',16.5,request,expected_audio=True)
    timeline=json.loads((root/'timeline.json').read_text(encoding='utf-8'))
    assert [segment['source_id'] for segment in timeline['segments']]==[
        segment['source_id'] for segment in reversed(plan['segments'])]
    assert timeline['segments'][0]['transition']=='fade'
    assert done['result']['duration_shortfall'] is False


def test_saved_timeline_revision_changes_visible_hook_and_audible_effect(owned_sources):
    import av
    import numpy as np

    request=JobRequest(source=owned_sources[0]['source'],rights_confirmed=True,workflow='highlights',
                       mode='longs',minimum=5,maximum=6,intervals=[(0,5)],review_before_render=True,
                       save_drive=False,audio_mode='silent',captions=False,max_text_model_calls=0)
    job=store.create(request.model_dump())
    process(store.claim('fixture'))
    root=config.SCRATCH/job['id']
    output=root/'clip-1.mp4'

    def render_revision(start):
        plan=store.get(job['id'])['result']['edit_plan']
        segment={'id':plan['segments'][0]['id'],'start_seconds':0,'end_seconds':5,'transition':'cut',
                 'hook':{'text':'TIMELINE','start':start,'end':start+.5},
                 'sounds':[{'kind':'impact','start':start,'gain':.5}]}
        submitted=store.edit_plan(job['id'],plan['revision'],[segment],None,approve=True)
        process(store.claim('fixture'))
        done=store.get(job['id'])
        assert done['state']=='READY',done['error']
        revision=submitted['revision']
        snapshot=root/f'timeline-r{revision}.json'
        assert json.loads(snapshot.read_text())==done['result']['render_timeline']
        return snapshot

    def sample(at):
        with av.open(str(output)) as container:
            video=next(frame for frame in container.decode(video=0) if frame.time>=at)
            lit=int((video.to_ndarray(format='gray')>180).sum())
        with av.open(str(output)) as container:
            audio=next(frame for frame in container.decode(audio=0) if frame.time>=at)
            peak=float(np.abs(audio.to_ndarray()).max())
        return lit,peak

    first=render_revision(.5)
    first_snapshot=first.read_bytes()
    lit,peak=sample(.6)
    assert lit>100 and peak>.03
    lit,peak=sample(1.6)
    assert lit==0 and peak<.001

    second=render_revision(1.5)
    assert first.read_bytes()==first_snapshot and second!=first
    lit,peak=sample(.6)
    assert lit==0 and peak<.001
    lit,peak=sample(1.6)
    assert lit>100 and peak>.03


def test_crossfade_overlaps_decoded_video_and_original_audio(tmp_path,monkeypatch):
    import av
    import numpy as np
    from factory.render_timeline import build, compile_scenes

    monkeypatch.setenv('FFMPEG_ENCODER','x264')
    paths=[]
    for color,frequency in [('green',250),('red',400),('blue',800)]:
        path=tmp_path/f'{color}.mp4'
        media.run([media.ffmpeg(),'-y','-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=30',
                   '-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000',
                   '-t','5','-c:v','libx264','-threads','2','-c:a','aac',str(path)])
        paths.append(path)
    request=JobRequest(source='upload:owned.mp4',rights_confirmed=True,mode='longs')
    candidates=[{'start_seconds':i*5,'end_seconds':i*5+5,'transition':'cut'} for i in range(3)]
    candidates[-1].update(transition='crossfade',transition_duration=1)
    timeline=build(candidates,request,{'source-1':15},1)
    scenes=compile_scenes(timeline,request)
    output=tmp_path/'crossfade.mp4'
    media.assemble_timeline(paths,output,scenes,request)
    report=media.validate_output(output,14,request,expected_audio=True)
    assert abs(report['duration']-14)<.1

    with av.open(str(output)) as container:
        frame=next(frame for frame in container.decode(video=0) if frame.time>=9.5)
        rgb=frame.to_ndarray(format='rgb24').mean(axis=(0,1))
    assert rgb[0]>80 and rgb[2]>80 and rgb[1]<30
    with av.open(str(output)) as container:
        audio=np.concatenate([frame.to_ndarray()[0] for frame in container.decode(audio=0)
                              if 9.4<=frame.time<=9.6])
    frequencies=np.fft.rfftfreq(len(audio),1/48000)
    spectrum=np.abs(np.fft.rfft(audio))
    assert all(max(spectrum[abs(frequencies-frequency)<8])>10 for frequency in (400,800))


def test_timeline_effects_change_decoded_frames_and_audio(tmp_path,monkeypatch):
    import av
    import numpy as np
    from factory.render_timeline import build, compile_scenes

    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setenv('FFMPEG_ENCODER','x264')
    (tmp_path/'logos').mkdir()
    (tmp_path/'backgrounds').mkdir()
    ffmpeg=[media.ffmpeg(),'-y','-v','error','-f','lavfi']
    source=tmp_path/'source.mp4'
    media.run([*ffmpeg,'-i','color=black:s=160x90:r=30','-f','lavfi','-i','sine=f=440:r=48000',
               '-vf',"geq=lum='16+12*T+40*gte(X,W/3)+30*gte(Y,H/3)':cb=128:cr=128",
               '-t','10.5','-c:v','libx264','-threads','2','-c:a','aac',str(source)])
    media.run([*ffmpeg,'-i','color=lime:s=160x90','-frames:v','1','-threads','1',str(tmp_path/'logos'/'green.png')])
    media.run([*ffmpeg,'-i','color=blue:s=160x90','-t','1','-c:v','libx264','-threads','2',
               str(tmp_path/'backgrounds'/'blue.mp4')])
    effects=[{'kind':'gain','start':.25,'end':.75,'gain':0},
             {'kind':'freeze_frame','start':1,'end':2}, {'kind':'slow_motion','start':3,'end':4},
             {'kind':'replay','start':5,'end':6,'replay_start':1},
             {'kind':'punch_in','start':6,'end':6.5,'scale':2},
             {'kind':'animated_zoom','start':6.5,'end':7,'scale':2},
             {'kind':'crop','start':7,'end':7.5,'scale':2,'x':1,'y':1},
             {'kind':'visual_accent','start':7.5,'end':8,'color':'#FF0000'},
             {'kind':'text_overlay','start':8,'end':8.5,'text':'TIMELINE'},
             {'kind':'image_overlay','start':8.5,'end':9,'asset':'green.png'},
             {'kind':'video_overlay','start':9,'end':9.5,'asset':'blue.mp4'},
             {'kind':'audio_fade','start':9.5,'end':10.5,'fade_direction':'out'}]
    request=JobRequest(source='upload:owned.mp4',rights_confirmed=True,mode='longs',captions=False)
    timeline=build([{'start_seconds':0,'end_seconds':10.5,'effects':effects}],request,{'source-1':10.5},1)
    scene=compile_scenes(timeline,request)[0]
    output=tmp_path/'effects.mp4'
    media.render(source,output,{'language':None,'segments':[]},0,10.5,scene.request,timeline_effects=scene.effects)
    samples={}
    times=[.9,1.3,1.8,3.1,3.8,4.1,5.35,6.25,6.75,7.2,7.8,8.25,8.75,9.25]
    with av.open(str(output)) as container:
        for frame in container.decode(video=0):
            if len(samples)<len(times) and frame.time>=times[len(samples)]:
                samples[times[len(samples)]]=frame.to_ndarray(format='rgb24')

    def corner(at):
        return float(samples[at][80,120,0])

    assert abs(corner(1.3)-corner(1.8))<3
    assert 0<corner(3.8)-corner(3.1)<9
    assert corner(4.1)-corner(5.35)>25
    assert corner(6.25)>corner(.9)+45 and corner(6.75)>corner(.9)+45
    assert corner(7.2)>corner(6.75)+25
    assert samples[7.8][4,40,0]>200 and samples[7.8][4,40,1]<60
    assert (samples[8.25][:,:,0]>240).sum()>500
    assert samples[8.75][360,640,1]>200 and samples[8.75][360,640,0]<60
    assert samples[9.25][360,640,2]>180 and samples[9.25][360,640,0]<60
    with av.open(str(output)) as container:
        peaks={}
        audio_times=[.4,.88,1.5,3.5,9.6,10.4]
        for frame in container.decode(audio=0):
            if len(peaks)<len(audio_times) and frame.time>=audio_times[len(peaks)]:
                peaks[audio_times[len(peaks)]]=float(np.abs(frame.to_ndarray()).max())
    assert peaks[.4]<.001 and peaks[.88]>.01 and peaks[1.5]<.001 and peaks[3.5]>.01
    assert peaks[10.4]<peaks[9.6]*.25


def test_render_recovers_after_transient_failure_without_rerendering_first_clip(owned_sources,monkeypatch):
    request=JobRequest(source=owned_sources[0]['source'],rights_confirmed=True,
                       workflow='highlights',minimum=5,maximum=6,intervals=[(0,5),(1,6)],
                       save_drive=False,audio_mode='silent',captions=False,preset='crop')
    job=store.create(request.model_dump())
    real_render = media.render
    rendered = []
    def render(source,output,*args,**kwargs):
        if output.name=='clip-2.mp4' and len(rendered)==1:
            rendered.append('interrupted')
            raise media.MediaFailure('SOURCE_UNAVAILABLE','injected failure',True)
        rendered.append(output.name)
        return real_render(source,output,*args,**kwargs)
    monkeypatch.setattr(media,'render',render)
    process(store.claim('fixture'))
    queued=store.get(job['id'])
    assert queued['state']=='QUEUED'
    assert queued['result']['failure']['code']=='SOURCE_UNAVAILABLE'
    with store.connect() as db:
        db.execute("UPDATE jobs SET result=json_remove(result,'$.retry_at') WHERE id=?",(job['id'],))
    process(store.claim('fixture'))
    done=store.get(job['id'])
    assert done['state']=='READY',done['error']
    assert rendered==['clip-1.mp4','interrupted','clip-2.mp4']
