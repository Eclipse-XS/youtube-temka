"""One checkpointed clipping pipeline for local and authenticated remote workers."""
import json
import math
import os
import re
import sys
import threading
import time
from . import config,store,media,render_timeline,stage_cache
from .models import JobRequest
from .highlights import analyze
from .resources import ResourcePeaks, preflight
from .cleanup import remove_workspace
from .progress import MODEL_PROGRESS, Progress
from jsonfile import write_json_atomic


class NeedsReview(ValueError):
    pass


def source_plan(source, request, root, progress):
    progress.begin('source','PROBING',message=source if source.startswith('upload:') else None)
    checkpoint = root/'source.json'
    identity=stage_cache.source_identity(source)
    shared=stage_cache.cache_path('probe',[1,identity]) if identity else None
    if checkpoint.is_file():
        metadata = json.loads(checkpoint.read_text(encoding='utf-8'))
        progress.reused('source_metadata')
        if metadata.get('local_identity') is not None and metadata['local_identity']!=identity:
            raise media.MediaFailure('SOURCE_CHANGED','The original upload changed after analysis. Submit the changed file as a new job.')
    else:
        metadata=stage_cache.read_json(shared)
        if metadata is not None:
            progress.reused('source_metadata')
        else:
            metadata = media.probe(source)
            if identity:
                metadata['local_identity']=identity
                stage_cache.save_json(shared,metadata)
        write_json_atomic(checkpoint, metadata, ensure_ascii=True)
    end = min(request.end or metadata['duration'],metadata['duration'])
    if end <= request.start:
        raise ValueError('Selected interval begins after the end of the source')
    if end-request.start > 86400:
        raise ValueError('Processing is bounded to 24 hours per source; select a shorter interval')
    available = [r for r in metadata['resolutions'] if request.resolution=='best' or r<=request.resolution]
    if media.local_source(source):
        height = max(metadata['resolutions'])
        available = [height if request.resolution=='best' else min(height,request.resolution)]
    if not available:
        raise ValueError('No source resolution at or below the selected quality is available')
    progress.done()
    return metadata,end,max(available)


def media_signals(source, request, metadata, end, resolution, root, progress):
    from .signals import MAX_WINDOWS, WINDOW_SECONDS, scan

    path = root/('gameplay-signals-v1.json' if request.gameplay_only else 'signals.json')
    if path.is_file():
        data = json.loads(path.read_text(encoding='utf-8'))
        progress.reused('visual_signals')
        return data['events'],data['scenes'],data['coverage']
    windows = math.ceil((end-request.start)/WINDOW_SECONDS)
    progress.begin('signals','ANALYZING',windows if request.gameplay_only else min(windows,MAX_WINDOWS),'windows')
    identity=metadata.get('local_identity')
    shared=stage_cache.cache_path('signals',[2,identity,request.start,end,resolution,request.gameplay_only,
                                            request.gameplay_scan_fps,WINDOW_SECONDS,MAX_WINDOWS]) if identity else None
    cached=stage_cache.read_json(shared)
    if cached is None:
        events,scenes,coverage = scan(source,request,metadata,end,resolution,root,progress.tick)
        cached={'events':events,'scenes':scenes,'coverage':coverage}
        stage_cache.save_json(shared,cached)
    else:
        progress.reused('visual_signals')
    write_json_atomic(path,cached)
    progress.done()
    return cached['events'],cached['scenes'],cached['coverage']


def rank_media(transcript, request, metadata, source, end, resolution, root, progress, signals):
    from .signals import gameplay_candidates, propose
    from .inference import installed_model_digest

    events,scenes,coverage=signals
    duration=end-request.start
    identity=metadata.get('local_identity')
    model=(request.visual_model if request.max_visual_model_calls else None) if request.gameplay_only else request.llm_model or config.MODEL
    digest=installed_model_digest(progress,model) if identity and model and (request.gameplay_only or request.max_text_model_calls) else None
    controls=(request.minimum,request.maximum,request.count,request.gameplay_focus,request.gameplay_low_signal_fraction,
              request.max_text_model_calls,request.max_visual_model_calls,request.max_model_context_tokens,
              request.max_model_output_tokens,request.max_model_seconds)
    shareable=bool(identity and (digest or (request.gameplay_only and not model)))
    shared=stage_cache.cache_path('selection',[3,identity,request.start,end,resolution,progress.source_id,controls,
                                               request.gameplay_only,model,digest,signals,transcript]) if shareable else None
    cached=stage_cache.read_json(shared)
    if cached is not None:
        progress.reused('candidate_discovery')
        return cached
    if request.gameplay_only:
        from .visual_review import review_candidates

        candidates=gameplay_candidates(events,scenes,request,duration,metadata['title'],coverage,progress.source_id)
        preview_resolution=max((r for r in metadata['resolutions'] if r<=min(resolution,480)),default=resolution)
        review_candidates(candidates,source,request,preview_resolution,root,progress)
        preferred={'comedy':{'npc_behavior','ragdoll','absurd_interaction'},
                   'physics':{'physics_glitch','animation_glitch','ragdoll'},
                   'stunts':{'vehicle_crash','stunt_fail','police_chase_fail'}}.get(request.gameplay_focus, set())
        for candidate in candidates:
            components=candidate['evidence']['score_components']
            bonus=6 if candidate['category'] in preferred else 0
            components.update(profile_bonus=bonus,technical_quality=min(1,resolution/720))
            candidate['score']=round(candidate['score']+bonus+5*bool(components['event_completeness']),3)
        candidates.sort(key=lambda candidate:-candidate['score'])
        result={'candidates':candidates,'analysis':'gameplay_signals','analysis_outcome':'editorial_review_required',
                'selection_summary':f'{len(candidates)} gameplay moments selected for review from sampled visual evidence.'}
    else:
        result=analyze(transcript,request,duration,progress.tick,propose(events,scenes,request,duration,metadata['title']))
    result={**result,'signal_coverage':coverage}
    complete_vision = not model or all(c.get('visual_review_state') in ('uncertain','model_hypothesis')
                                      for c in result['candidates'][:request.max_visual_model_calls])
    if (request.gameplay_only and complete_vision) or result['analysis']=='ollama':
        stage_cache.save_json(shared,result)
    return result


def compilation_plan(request, root, progress, update, previous=None):
    from .compilation import plan_gameplay, select

    sources = {}
    groups = []
    for index, item in enumerate(request.sources,1):
        key = item.source_id
        progress.source_id = key
        folder = root/key
        folder.mkdir(exist_ok=True)
        options = request.model_copy(update={'start':item.start,'end':item.end,'language':item.language or request.language})
        try:
            metadata,end,resolution = source_plan(item.source,options,folder,progress)
            if any(b>end for _,b in item.exclude):
                raise ValueError('An excluded interval extends beyond the source')
            checkpoint = folder/'analysis.json'
            if checkpoint.is_file():
                result = json.loads(checkpoint.read_text(encoding='utf-8'))
            else:
                transcript = discovery_transcript(item.source,options,folder,metadata,end,resolution,progress,lambda **_:None)
                signals = media_signals(item.source,options,metadata,end,resolution,folder,progress)
                progress.begin('highlights','ANALYZING',message=f'Source {index}/{len(request.sources)}')
                result = rank_media(transcript,options,metadata,item.source,end,resolution,folder,progress,signals)
                write_json_atomic(checkpoint,result,ensure_ascii=True)
                del transcript
                progress.done()
        except (ValueError, RuntimeError) as error:
            update(result={'failed_source_id':key})
            if isinstance(error, media.MediaFailure):
                raise media.MediaFailure(error.code, f'Source {index}: {error}', error.retryable) from error
            raise
        sources[key] = {'source':item.source,'metadata':metadata,'resolution':resolution,'end':end,'language':options.language,
                        'signal_coverage':result.get('signal_coverage')}
        groups.append([{**c,'source_id':key,'source_offset':item.start,
                        'source_priority':item.priority,'source_max_contribution':item.max_contribution}
                       for c in result['candidates'] if all(
                           c['end_seconds']+item.start<=a or c['start_seconds']+item.start>=b
                           for a,b in item.exclude)])
        update(result={'sources':sources,'failed_source_id':None})
    progress.source_id = None
    if previous is not None:
        return sources, previous
    target = request.target_duration or 900
    narrative = None
    if request.gameplay_only:
        selected,duration,narrative = plan_gameplay(groups,request.count,target,
                                                    {item.source_id:item for item in request.sources})
    else:
        selected,duration = select(groups,request.count,target)
    result = {'candidates':selected, 'analysis':'gameplay_narrative' if narrative is not None else 'source_aware_compilation',
              'selection_summary':f'Selected {duration:.1f}s for a {target:g}s target from {len({c["source_id"] for c in selected})} sources.',
              'target_duration':target,'planned_duration':round(duration,3),
              'duration_shortfall':duration<target*.95}
    if narrative is not None:
        result['narrative_plan'] = narrative
    if result['duration_shortfall']:
        result['selection_summary'] += ' Add more suitable material or adjust the target/clip constraints.'
    return sources,result


def transcript_artifacts(root, transcript, duration, *, replace=False):
    from subtitles import generate_srt

    srt = root/'transcript.srt'
    if replace or not srt.is_file():
        if not generate_srt(transcript,0,duration,str(srt)):
            srt.write_text('',encoding='utf-8')
    vtt = root/'transcript.vtt'
    if replace or not vtt.is_file():
        with srt.open(encoding='utf-8-sig') as source, vtt.open('w',encoding='utf-8') as output:
            output.write('WEBVTT\n\n')
            for line in source:
                output.write(re.sub(r'(\d\d:\d\d:\d\d),(\d{3})',r'\1.\2',line))


def empty_transcript(language=None):
    return {'language':language,'segments':[],'text':''}


def save_edit_transcript(root,name,transcript,start,end):
    from .compilation import append_transcript

    retained=empty_transcript(transcript.get('language'))
    append_transcript(retained,transcript,start,end,0)
    if not retained['segments']:
        (root/name).unlink(missing_ok=True)
        return None
    retained['text']=' '.join(segment['text'] for segment in retained['segments'])
    write_json_atomic(root/name,retained,ensure_ascii=True)
    return name


def reuse_edit_transcript(root,origin_job,output,request,tick):
    name=output.get('edit_transcript')
    checkpoint=root/'transcript.json'
    if (not name or not re.fullmatch(r'edit-(?:clip-\d+|long)\.json',name)
        or checkpoint.is_file() or request.start!=0 or any(
            getattr(request,key)!=origin_job['request'].get(key) for key in ('asr_model','language'))):
        return
    local=config.SCRATCH/origin_job['id']/name
    if local.is_file():
        write_json_atomic(checkpoint,json.loads(local.read_text(encoding='utf-8')),ensure_ascii=True)
    elif name in origin_job['result'].get('artifacts',{}):
        media.fetch_drive(origin_job['result']['artifacts'][name],checkpoint,tick)


def discovery_transcript(source,request,root,metadata,end,resolution,progress,update):
    if request.gameplay_only:
        progress.done('transcription','skipped','Gameplay discovery scans visual and audio signals first')
        return empty_transcript(request.language)
    return transcribe_chunks(source,request,root,metadata,end,resolution,progress,update)


def transcribe_chunks(source,request,root,metadata,end,resolution,progress,update,*,operation_prefix=''):
    path=root/'transcript.json'
    if path.is_file():
        progress.done('extraction',message='Reused transcript checkpoint');progress.done('transcription',message='Reused transcript checkpoint')
        progress.reused('asr')
        return json.loads(path.read_text(encoding='utf-8'))
    duration=end-request.start
    segments=[];language=request.language
    silent_short=request.audio_mode=='silent' and not request.captions and request.minimum<=duration<=request.maximum
    if metadata.get('has_audio',True) and not (request.intervals and not request.captions) and not silent_short:
        # Keep the original chunk size on retry: changing it would reuse partial
        # transcripts for different intervals. Pre-manifest checkpoints used 900s.
        plan=root/'asr-chunks.json'
        if plan.is_file():
            chunk_seconds=int(json.loads(plan.read_text(encoding='utf-8'))['seconds'])
            if not 60<=chunk_seconds<=900:raise ValueError('Invalid ASR chunk checkpoint')
        else:
            legacy=any(p.stem.removeprefix('transcript-').isdigit() for p in root.glob('transcript-*.json'))
            chunk_seconds=900 if legacy else config.AUDIO_CHUNK_SECONDS
            write_json_atomic(plan,{'seconds':chunk_seconds})
        chunks=math.ceil(duration/chunk_seconds)
        identity=metadata.get('local_identity')
        model=request.asr_model or config.ASR_MODEL
        for index in range(chunks):
            offset=index*chunk_seconds;chunk_end=min(offset+chunk_seconds,duration)
            partial=root/f'transcript-{offset}.json'
            dependency=[1,identity,request.start+offset,request.start+chunk_end,resolution,request.language,model,
                        os.environ.get('WHISPER_DEVICE'),os.environ.get('WHISPER_COMPUTE'),os.environ.get('WHISPER_MODEL_PATH')]
            shared=stage_cache.cache_path('asr',dependency) if identity else None
            if not partial.is_file():
                retained=stage_cache.read_json(shared)
                if retained is not None:
                    write_json_atomic(partial,retained)
                    progress.reused('asr')
            if not partial.is_file():
                operation=f'{operation_prefix}chunk-{offset}'
                progress.begin('extraction','DOWNLOADING',message=f'Audio chunk {index+1}/{chunks}',operation=operation)
                audio=root/f'audio-{offset}.mka'
                cached_audio=stage_cache.cache_path('audio',dependency[:5],'.mka') if identity else None
                if stage_cache.restore_file(cached_audio,audio):
                    progress.reused('audio_extraction')
                else:
                    media.download(source,audio,request.start+offset,request.start+chunk_end,resolution,True,progress.tick)
                    stage_cache.save_file(cached_audio,audio)
                progress.done()
                progress.begin('transcription','TRANSCRIBING',chunk_end-offset,'seconds',
                               f'Chunk {index+1}/{chunks}',operation=operation,model=model)
                media.run([sys.executable,'-m','factory.transcribe',str(audio),str(partial),language or 'auto'],progress.tick,duration=chunk_end-offset,env={**os.environ,'WHISPER_MODEL':model})
                stage_cache.save_json(shared,json.loads(partial.read_text(encoding='utf-8')))
                progress.done()
            (root/f'audio-{offset}.mka').unlink(missing_ok=True)
            part=json.loads(partial.read_text(encoding='utf-8'))
            if part['segments']:language=language or part.get('language')
            for segment in part['segments']:
                segment['start']+=offset;segment['end']+=offset
                for word in segment.get('words',[]):
                    word['start']+=offset;word['end']+=offset
                segments.append(segment)
            update(result={'audio_chunks_completed':index+1,'audio_chunks_total':chunks})
    else:
        progress.done('extraction','skipped','No audio, manual intervals without captions, or an explicitly silent short source')
        progress.done('transcription','skipped','No speech analysis required')
    transcript={'language':language if segments or request.language else None,'segments':segments,'text':' '.join(s['text'] for s in segments)}
    write_json_atomic(path,transcript,ensure_ascii=True)
    return transcript


def gameplay_clip_transcript(source,request,root,metadata,resolution,progress,candidate,offset,index):
    from .compilation import append_transcript

    start,end=candidate['start_seconds'],candidate['end_seconds']
    merged=empty_transcript(request.language)
    if not (request.captions or (request.audio_mode=='voiceover' and not request.tts_text)) or metadata.get('has_audio') is False:
        return merged
    key=render_timeline.fingerprint([source,offset+start,offset+end,resolution,request.language,request.asr_model])
    folder=root/f'gameplay-asr-{key}'
    folder.mkdir(exist_ok=True)
    options=request.model_copy(update={'start':offset+start,'end':offset+end,'intervals':[]})
    selected=transcribe_chunks(source,options,folder,metadata,options.end,resolution,progress,lambda **_:None,
                               operation_prefix=f'clip-{index}-')
    append_transcript(merged,selected,0,end-start,start)
    return merged


def process(claim,assets=None):
    job=claim['job'];jid=job['id'];lease=claim['lease']
    root=config.SCRATCH/jid;stage='PROBING'
    cancel_event=threading.Event()
    def update(state=None,**kwargs):
        nonlocal stage
        if state:stage=state
        store.update(jid,lease,state=state,**kwargs)
    progress=Progress(update)
    peaks=ResourcePeaks()
    model_context=MODEL_PROGRESS.set(progress)
    def renew():
        renewal=time.monotonic()+15
        while not cancel_event.wait(2):
            if time.monotonic()>=renewal:
                try:store.update(jid,lease)
                except Exception:return
                renewal=time.monotonic()+15
            peaks.sample()
    heartbeat=threading.Thread(target=renew,daemon=True);heartbeat.start()
    try:
        request=JobRequest.model_validate(job['request'])
        preview_timeline=job['result'].get('preview_pending')
        preview=preview_timeline is not None
        progress.limit_models(request,claim.get('model_usage',{}))
        root.mkdir(parents=True,exist_ok=True)
        if job['result'].get('cloud_verified'):
            remove_workspace(root);update('READY');return
        preflight();source=request.source
        if source.startswith('edit:'):
            _,origin,index=source.split(':')
            origin_job=store.get(origin)
            original=origin_job['result']['outputs'][int(index)]
            if not original.get('edit_source'):raise NeedsReview('This older output has no preserved editable source. Re-upload the original once.')
            editable=original['edit_source']
            if editable.get('local'):
                name=editable['local']
                if not re.fullmatch(r'(selected-\d+|long-source)\.mp4',name):raise ValueError('Invalid preserved local source')
                path=config.SCRATCH/origin/name
                if not (root/'edit-source.mp4').is_file():
                    preflight(path.stat().st_size)
                    if not stage_cache.restore_file(path,root/'edit-source.mp4'):
                        raise ValueError('Preserved editable source could not be copied')
            else:media.fetch_drive(editable,root/'edit-source.mp4',progress.tick)
            reuse_edit_transcript(root,origin_job,original,request,progress.tick)
            source='job-local:'+jid
        compiling = request.workflow=='compilation'
        analysis_checkpoint=root/'analysis.json'
        source_url=request.source if request.source.startswith('https://') else origin_job['result'].get('source_url') if request.source.startswith('edit:') else None
        if compiling:
            source_url = None
            previous=json.loads(analysis_checkpoint.read_text(encoding='utf-8')) if analysis_checkpoint.is_file() else None
            sources,result = compilation_plan(request,root,progress,update,previous)
            metadata = {'title':'Highlights compilation','platform':'compilation'}
            update(result={'source':metadata,'source_url':None})
            end = request.start + result['planned_duration']
        else:
            progress.source_id = 'source-1'
            metadata,end,resolution = source_plan(source,request,root,progress)
            if request.workflow=='story':
                from .timeline import story_part_count
                story_part_count(request,end-request.start)
            update(result={'source':metadata,'source_url':source_url,'actual_resolution':resolution,'source_start':request.start,'processing_end':end,'ingest_strategy':'audio-first bounded chunks' if metadata.get('independent_audio',True) else 'bounded muxed segments: independent audio stream unavailable'})
        background=config.DATA/'backgrounds'/request.background if request.background else next(iter(sorted((config.DATA/'backgrounds').glob('*.mp4'))),None)
        if request.background_mode=='none':background=None
        if request.background_mode=='random':
            import random
            choices=sorted((config.DATA/'backgrounds').glob('*.mp4'))
            background=random.Random(jid).choice(choices) if choices else None
        if assets is not None:background=assets.get('backgrounds')
        if request.background_mode=='none':background=None
        if request.mode=='shorts' and request.preset=='gameplay' and (not background or not background.is_file()):raise NeedsReview('Add an authorized background asset or select Automatic / Blurred Background')
        if compiling:
            transcript = {'language':None,'segments':[]}
        else:
            transcript=discovery_transcript(source,request,root,metadata,end,resolution,progress,update)
            progress.begin('language','TRANSCRIBING')
            update(result={'language':transcript['language']})
            progress.done(message='Detected '+str(transcript['language']) if transcript['language'] else 'No speech detected')
            if not request.gameplay_only:
                transcript_artifacts(root,transcript,end-request.start)
        scan_needed = (not compiling and request.workflow in ('story','highlights') and not request.intervals
                       and not analysis_checkpoint.is_file() and not job['result'].get('candidates'))
        signals = media_signals(source,request,metadata,end,resolution,root,progress) if scan_needed else None
        progress.begin('highlights','ANALYZING')
        if compiling:
            candidates = result['candidates']
        elif analysis_checkpoint.is_file():
            result=json.loads(analysis_checkpoint.read_text(encoding='utf-8'));candidates=result['candidates']
        elif job['result'].get('candidates'):
            # Another worker may own the old scratch volume. The controller's
            # saved selection still fences clip identity across that handoff.
            result={key:job['result'][key] for key in ('candidates','analysis','model','analysis_outcome','analysis_diagnostics','selection_summary','series_applied','signal_coverage') if key in job['result']}
            candidates=result['candidates']
        elif request.intervals:
            if any(b>end for a,b in request.intervals):raise ValueError('Manual interval extends beyond the actual source duration')
            candidates=[{'start_seconds':a-request.start,'end_seconds':b-request.start,'title':metadata['title']} for a,b in (request.intervals if request.mode=='longs' else sorted(request.intervals))]
            result={'candidates':candidates,'analysis':'manual chronological intervals'}
        elif request.workflow in ('story','highlights'):
            if request.workflow=='story':
                from .timeline import story
                _,scenes,coverage=signals
                candidates,summary = story(transcript,request,end-request.start,metadata['title'],scenes)
                result = {'candidates':candidates,'analysis':'continuous_story','selection_summary':summary,
                          'series_applied':True,'signal_coverage':coverage}
            else:
                result = rank_media(transcript,request,metadata,source,end,resolution,root,progress,signals)
                candidates = result['candidates']
        elif not transcript['segments'] and request.minimum<=end-request.start<=request.maximum and request.audio_mode=='silent':
            candidates=[{'start_seconds':0,'end_seconds':end-request.start,'title':metadata['title']}]
            result={'candidates':candidates,'analysis':'whole short visual source; no AI claim'}
        else:
            result=analyze(transcript,request,end-request.start,progress.tick);candidates=result['candidates']
            if request.mode=='longs':candidates.sort(key=lambda c:c['start_seconds'])
        if request.series_mode=='connected' and not result.get('series_applied'):
            from .timeline import connected
            candidates,summary=connected(candidates,request,end-request.start)
            result.update(candidates=candidates,selection_summary=summary,series_applied=True)
        if request.mode=='longs' and not compiling and request.target_duration and not analysis_checkpoint.is_file() and not request.intervals:
            selected=[];remaining=request.target_duration
            for candidate in candidates:
                if remaining<request.minimum:break
                item=dict(candidate)
                length=item['end_seconds']-item['start_seconds']
                if length>remaining:
                    item['end_seconds']=item['start_seconds']+remaining;item['editorial_review_required']=True
                selected.append(item);remaining-=min(length,remaining)
            candidates=selected;result['candidates']=candidates
        if candidates:write_json_atomic(analysis_checkpoint,result,ensure_ascii=True)
        update(result=result);progress.done()
        if not candidates:
            raise NeedsReview('No suitable moments were found. Add source material, change the selected ranges, or select a manual interval.')
        if request.review_before_render and request.workflow in ('highlights','compilation'):
            review = job['result'].get('edit_plan')
            if review and not review['approved'] and not preview:
                update('REVIEW')
                return
            if not review:
                review_sources = ({key:{'title':item['metadata']['title'],'source':item['source'],'end':item['end']}
                                   for key,item in sources.items()} if compiling else
                                  {'source-1':{'title':metadata['title'],'source':request.source,'end':end}})
                review = {'version':1,'revision':1,'approved':False,'sources':review_sources,
                          'target_duration':result.get('target_duration'),
                          'intro':request.intro.model_dump() if request.intro else None,
                          'outro':request.outro.model_dump() if request.outro else None,
                          'chapter_titles':request.chapter_titles,
                          'segments':[{**candidate,'id':i+1,'source_id':candidate.get('source_id','source-1'),
                                       'source_offset':candidate.get('source_offset',request.start),
                                       'transition':request.transition} for i,candidate in enumerate(candidates)]}
                update('REVIEW',result={'edit_plan':review})
                return
            candidates = review['segments']
            result['candidates'] = candidates
            if compiling:
                selected = sum(c['end_seconds']-c['start_seconds'] for c in candidates)
                target = review['target_duration']
                result.update(planned_duration=round(selected,3),target_duration=target,
                              duration_shortfall=selected<target*.95,
                              selection_summary=f'Edited plan: {selected:.1f}s for a {target:g}s target.')
            update(result=result)
        source_limits={key:item['end'] for key,item in sources.items()} if compiling else {'source-1':end}
        saved_timeline=preview_timeline or job['result'].get('render_timeline')
        timeline_path=root/'timeline.json'
        if saved_timeline is None and timeline_path.is_file():
            checkpoint=json.loads(timeline_path.read_text(encoding='utf-8'))
            if checkpoint.get('schema_version')==render_timeline.SCHEMA_VERSION:
                saved_timeline=checkpoint
        timeline=saved_timeline or render_timeline.build(
            candidates,request,source_limits,job['result'].get('edit_plan',{}).get('revision',1),
            result.get('target_duration') if compiling else None)
        scenes=render_timeline.compile_scenes(timeline,request)
        cards=render_timeline.cards_for(timeline)
        revision_path=root/f"timeline-r{timeline['revision']}.json"
        if not revision_path.is_file():
            write_json_atomic(revision_path,timeline,ensure_ascii=True)
        if not preview:
            write_json_atomic(timeline_path,timeline,ensure_ascii=True)
        candidates=[scene.candidate for scene in scenes]
        update(result={'timeline_revision':timeline['revision']})
        force_audio=request.mode=='longs' and any(scene.sounds for scene in scenes)
        outputs=[];raw_sources={}
        last_source = None
        compilation_ranges = []
        hook_bindings=dict(job['result'].get('timeline_hook_bindings') or {})
        for i,scene in enumerate(scenes):
            candidate,clip_request=scene.candidate,scene.request
            automatic_hook,sounds,transition_seconds=scene.automatic_hook,scene.sounds,scene.fade_seconds
            progress.source_id = candidate.get('source_id','source-1')
            operation=f'clip-{i+1}'
            clip_transcript = transcript
            clip_source = source
            offset = candidate['source_offset']
            if compiling:
                from .compilation import append_transcript
                key = candidate['source_id']
                clip_source = sources[key]['source']
                clip_request.language = sources[key]['language']
                resolution = sources[key]['resolution']
                offset = candidate['source_offset']
                if not request.gameplay_only and key!=last_source:
                    source_transcript = json.loads((root/key/'transcript.json').read_text(encoding='utf-8'))
                    last_source = key
                if not request.gameplay_only:
                    clip_transcript = source_transcript
            if request.gameplay_only:
                clip_metadata=sources[key]['metadata'] if compiling else metadata
                speech_request=clip_request if scene.caption_cues is None else clip_request.model_copy(update={'captions':False})
                clip_transcript=gameplay_clip_transcript(clip_source,speech_request,root,clip_metadata,resolution,progress,candidate,offset,i+1)
                if not compiling:
                    from .compilation import append_transcript
                    append_transcript(transcript,clip_transcript,candidate['start_seconds'],candidate['end_seconds'],candidate['start_seconds'])
            if compiling:
                length = candidate['end_seconds']-candidate['start_seconds']
                scene_start = scene.start_ms / 1000
                append_transcript(transcript,clip_transcript,candidate['start_seconds'],candidate['end_seconds'],scene_start)
                compilation_ranges.append({**candidate,'start_seconds':scene_start,'end_seconds':scene_start+length})
            hook_candidates=None
            if automatic_hook:
                from .hooks import suggest, suggest_gameplay
                progress.begin('hooks','ANALYZING',message=f'Clip {i+1}/{len(candidates)}',operation=operation)
                evidence=' '.join(s['text'] for s in clip_transcript['segments'] if s['end']>candidate['start_seconds'] and s['start']<candidate['end_seconds'])
                language=request.metadata_language or clip_transcript['language'] or 'en'
                basis=candidate.get('visual_review') if request.gameplay_only else evidence
                hook_key=render_timeline.fingerprint([2,automatic_hook,basis,language,request.llm_model,metadata['title'],
                    candidate['start_seconds'],candidate['end_seconds'],candidate['source_offset']])
                hook_checkpoint=root/f'hook-{hook_key}.json'
                binding=hook_bindings.get(automatic_hook)
                if binding and binding['key']==hook_key:
                    hook_candidates=binding['decision']
                elif hook_checkpoint.is_file():
                    hook_candidates=json.loads(hook_checkpoint.read_text(encoding='utf-8'))
                else:
                    from .inference import installed_model_digest
                    model=request.llm_model or config.MODEL
                    digest=installed_model_digest(progress,model) if not request.gameplay_only and evidence and request.max_text_model_calls else None
                    shared=stage_cache.cache_path('hooks',[2,basis,language,metadata['title'],digest,
                        candidate['start_seconds'],candidate['end_seconds'],candidate['source_offset']]) if request.gameplay_only or digest else None
                    hook_candidates=stage_cache.read_json(shared)
                    if hook_candidates is None:
                        hook_candidates=(suggest_gameplay(candidate,language) if request.gameplay_only else
                                         suggest(evidence,language,request.llm_model,metadata['title']))
                        if request.gameplay_only or hook_candidates['method']=='ollama':
                            stage_cache.save_json(shared,hook_candidates)
                    else:
                        progress.reused('hooks')
                    write_json_atomic(hook_checkpoint,hook_candidates,ensure_ascii=True)
                if not binding or binding['key']!=hook_key:
                    hook_bindings[automatic_hook]={'key':hook_key,'decision':hook_candidates}
                    update(result={'timeline_hook_bindings':hook_bindings})
                suggestions=hook_candidates['candidates']
                clip_request.hook=suggestions[0]['text'] if suggestions else ''
                progress.done(message=hook_candidates['method'])
            duration=candidate['end_seconds']-candidate['start_seconds']
            output=root/(f'proxy-clip-{i+1}.mp4' if preview else f'clip-{i+1}.mp4')
            clip=root/f'selected-{i+1}.mp4'
            identity=stage_cache.source_identity(clip_source)
            source_key=render_timeline.fingerprint([2,identity or [jid,clip_source],offset+candidate['start_seconds'],
                                                    offset+candidate['end_seconds'],resolution,request.output_height,compiling])
            clip_checkpoint=clip.with_suffix('.json')
            cached_clip=stage_cache.cache_path('selected',source_key,'.mp4')
            source_binding=stage_cache.read_json(clip_checkpoint)
            valid_clip=(clip.is_file() and isinstance(source_binding,dict) and source_binding.get('key')==source_key
                        and source_binding.get('file')==stage_cache.file_identity(clip))
            speech=[item for item in clip_transcript['segments'] if item['end']>candidate['start_seconds'] and item['start']<candidate['end_seconds']]
            from .assets import timeline_asset_identities
            asset_versions=timeline_asset_identities(clip_request,background,scene.effects,assets)
            render_key=render_timeline.fingerprint([3,source_key,clip_request.model_dump(),[sound.model_dump() for sound in sounds],
                                                    force_audio,transition_seconds,[effect.model_dump() for effect in scene.effects],
                                                    scene.caption_cues,preview,speech,asset_versions,os.environ.get('FFMPEG_ENCODER')])
            progress.begin('retrieval','RENDERING',message=f'Clip {i+1}/{len(candidates)}',operation=operation)
            if not valid_clip:
                clip.unlink(missing_ok=True)
                if stage_cache.restore_file(cached_clip,clip):
                    progress.reused('selected_media')
                elif compiling:
                    local = media.local_source(clip_source)
                    if local:
                        media.normalize_compilation(local,clip,duration,request.output_height,progress.tick,
                                                    start=offset+candidate['start_seconds'],input_height=resolution)
                    else:
                        temporary = clip.with_suffix('.input.mp4')
                        try:
                            media.download(clip_source,temporary,offset+candidate['start_seconds'],offset+candidate['end_seconds'],resolution,False,progress.tick)
                            media.normalize_compilation(temporary,clip,duration,request.output_height,progress.tick)
                        finally:
                            temporary.unlink(missing_ok=True)
                else:
                    media.download(clip_source,clip,offset+candidate['start_seconds'],offset+candidate['end_seconds'],resolution,False,progress.tick)
                write_json_atomic(clip_checkpoint,{'key':source_key,'file':stage_cache.file_identity(clip)})
                stage_cache.save_file(cached_clip,clip)
            else:
                progress.reused('selected_media')
            raw_sources[output.name]=clip;progress.done()
            def render_stage(key,**details):
                if progress.active in ('rendering','captions_audio'):progress.done()
                progress.begin(key,'RENDERING',duration if key=='rendering' else None,'seconds' if key=='rendering' else None,
                               f'Clip {i+1}/{len(candidates)}',operation=operation,**details)
            cache_render=stage_cache.cache_path('render',render_key,'.mp4')
            report_path=output.with_suffix('.validation.json')
            current_report=stage_cache.read_json(report_path)
            if output.is_file() and (not current_report or current_report.get('timeline_render_key')!=render_key):
                output.unlink()
            if not output.is_file() and stage_cache.restore_file(cache_render.with_suffix('.json'),report_path):
                if stage_cache.restore_file(cache_render,output):
                    for suffix in ('.ass','.srt'):
                        output.with_suffix(suffix).unlink(missing_ok=True)
                        stage_cache.restore_file(cache_render.with_suffix(suffix),output.with_suffix(suffix))
                    output.with_suffix('.jpg').unlink(missing_ok=True)
            if output.is_file():
                try:
                    checkpoint=json.loads(output.with_suffix('.validation.json').read_text(encoding='utf-8'))
                    if checkpoint.get('timeline_render_key')!=render_key:
                        raise ValueError('Timeline render inputs changed')
                    refreshed=media.verify_checkpoint(output,checkpoint,clip_request,preview=preview)
                    if refreshed is not checkpoint:
                        write_json_atomic(output.with_suffix('.validation.json'),refreshed)
                    progress.done('captions_audio','skipped','Reused validated render');progress.done('rendering',message='Reused validated render')
                    progress.reused('scene_render')
                    progress.begin('validation','RENDERING',operation=operation)
                except Exception:output.unlink()
            if not output.is_file():
                for suffix in ('.jpg','.translated.json','.ass','.srt','.voice.json'):
                    output.with_suffix(suffix).unlink(missing_ok=True)
                media.render(clip,output,clip_transcript,candidate['start_seconds'],candidate['end_seconds'],
                             clip_request,background,progress.tick,stage=render_stage,
                             music_path=assets.get('music') if assets is not None else None,
                             logo_path=assets.get('logos') if assets is not None else None,
                             timeline_sounds=sounds,force_audio=force_audio,transition_seconds=transition_seconds,
                             timeline_effects=scene.effects,asset_paths=assets,caption_cues=scene.caption_cues,preview=preview)
                if report_path.is_file():
                    report=json.loads(report_path.read_text(encoding='utf-8'))
                    write_json_atomic(report_path,{**report,'timeline_render_key':render_key})
                    stage_cache.save_file(cache_render,output)
                    if cache_render.is_file():
                        stage_cache.save_json(cache_render.with_suffix('.json'),{**report,'timeline_render_key':render_key})
                        for suffix in ('.ass','.srt'):
                            if output.with_suffix(suffix).is_file():
                                stage_cache.save_file(cache_render.with_suffix(suffix),output.with_suffix(suffix))
            progress.done('validation')
            validation=json.loads(output.with_suffix('.validation.json').read_text()) if output.with_suffix('.validation.json').is_file() else {}
            if preview:
                outputs.append({'name':output.name,'duration':validation.get('duration',duration)})
                continue
            thumbnail=output.with_suffix('.jpg')
            from .thumbnails import create as make_thumbnail
            progress.begin('thumbnail','RENDERING',operation=operation)
            thumbnail_report=make_thumbnail(output,thumbnail,tick=progress.tick) if not thumbnail.is_file() else {'method':'reused_existing_frame'}
            progress.done()
            outputs.append({'name':output.name,'title':candidate['title'],'approved':False,'duration':validation.get('duration',duration),'edit_duration':duration,'thumbnail':{'name':thumbnail.name,**thumbnail_report},'validation':validation})
            if clip_request.captions and output.with_suffix('.ass').is_file():
                outputs[-1]['caption_artifact']=output.with_suffix('.ass').name
            if clip_request.cta_text:
                outputs[-1]['cta']=clip_request.cta_text
            retained=save_edit_transcript(root,f'edit-clip-{i+1}.json',clip_transcript,candidate['start_seconds'],candidate['end_seconds'])
            if retained:
                outputs[-1]['edit_transcript']=retained
            digest=validation.get('media_fingerprint',{}).get('sha256') or media.media_fingerprint(output)['sha256']
            outputs[-1].update(render_id=f'{jid}:{i+1}',render_version=1,output_hash=digest,hook=clip_request.hook,hook_candidates=hook_candidates,series={'id':jid,'title':candidate.get('series_title',candidate['title']),'part':candidate['part'],'parts':candidate['parts'],'previous_part':candidate['part']-1 if candidate['part']>1 else None,'next_part':candidate['part']+1 if candidate['part']<candidate['parts'] else None} if candidate.get('part') else None)
            update(result={'outputs':outputs,'clips_completed':i+1,'clips_total':len(candidates)})
        progress.source_id = None
        if not preview and (compiling or request.gameplay_only):
            transcript['segments'].sort(key=lambda segment:segment['start'])
            transcript['text'] = ' '.join(s['text'] for s in transcript['segments'])
            write_json_atomic(root/'transcript.json',transcript,ensure_ascii=True)
            transcript_artifacts(root,transcript,timeline['duration_ms']/1000 if compiling else end-request.start,replace=True)
            update(result={'language':transcript['language']})

        def finish_preview(files):
            width,height=media.delivery_dimensions(request,True)
            update('REVIEW',result={'preview_pending':None,'cache_hits':progress.cache_hits,
                                    'preview':{'revision':timeline['revision'],'files':files,'width':width,'height':height}})

        if request.mode=='longs' and (len(outputs)>1 or cards):
            playlist=[*scenes]
            video_paths=[root/o['name'] for o in outputs]
            source_paths=list(raw_sources.values())
            for kind,card in cards.items():
                key=render_timeline.fingerprint([card.settings.model_dump(),request.output_height,preview])[:24]
                path=root/f'card-{kind}-{key}.mp4'
                progress.begin('rendering','RENDERING',operation=f'card-{kind}')
                if not path.is_file():
                    media.render_card(path,card,request,progress.tick,preview=preview)
                progress.done()
                index=int(card.settings.after_cold_open) if kind=='intro' else len(playlist)
                playlist.insert(index,card)
                video_paths.insert(index,path)
                source_paths.insert(index,path)
            progress.begin('rendering','RENDERING',operation='assemble-long')
            final=root/('proxy-long.mp4' if preview else 'long.mp4')
            media.assemble_timeline(video_paths,final,playlist,request,progress.tick,reencode=bool(cards),preview=preview)
            progress.done()
            progress.begin('validation','RENDERING',operation='assemble-long')
            duration=timeline['duration_ms']/1000 if cards else sum(o['duration'] for o in outputs)-sum(s.overlap_ms for s in scenes)/1000
            validation=media.validate_output(final,duration,request=request,preview=preview)
            progress.done()
            if preview:
                finish_preview([final.name])
                return
            progress.begin('retrieval','RENDERING',operation='assemble-edit-source')
            raw=root/'long-source.mp4';media.assemble_timeline(source_paths,raw,playlist,request,progress.tick,reencode=bool(cards))
            progress.done()
            raw_sources[final.name]=raw
            progress.begin('thumbnail','RENDERING',operation='assemble-long')
            thumb=final.with_suffix('.jpg');thumbnail_report=make_thumbnail(final,thumb,tick=progress.tick)
            progress.done()
            from .compilation import append_transcript
            edit_speech=empty_transcript()
            for item,scene in zip(outputs,scenes):
                if item.get('edit_transcript'):
                    part=json.loads((root/item['edit_transcript']).read_text(encoding='utf-8'))
                    append_transcript(edit_speech,part,0,item['edit_duration'],scene.start_ms/1000)
            edit_duration=timeline['duration_ms']/1000
            retained=save_edit_transcript(root,'edit-long.json',edit_speech,0,edit_duration)
            outputs=[{'name':final.name,'title':metadata['title'],'approved':False,'duration':validation['duration'],'edit_duration':edit_duration,'validation':validation,'thumbnail':{'name':thumb.name,**thumbnail_report}}]
            if retained:
                outputs[0]['edit_transcript']=retained
            digest=media.media_fingerprint(final)['sha256']
            outputs[0].update(render_id=f'{jid}:long',render_version=1,output_hash=digest)
        if preview:
            finish_preview([item['name'] for item in outputs])
            return
        if compiling:
            actual = outputs[0]['duration']
            target = result['target_duration']
            update(result={'actual_duration':actual,'duration_shortfall':actual<target*.95,
                           'within_target_duration':target*.95<=actual<=target*1.05})
        from . import metadata as publishing_metadata
        from .editorial import assess
        evidence_ranges = compilation_ranges if compiling else candidates
        contexts=[publishing_metadata.context(transcript,request,metadata,evidence_ranges if request.mode=='longs' else evidence_ranges[i:i+1],output,source_url) for i,output in enumerate(outputs)]
        prior_outputs=job['result'].get('previous_timeline_outputs') or job['result'].get('outputs',[])
        previous=[o.get('publishing_metadata') for o in prior_outputs]
        progress.begin('metadata','ANALYZING',len(outputs),'clips')
        drafts=publishing_metadata.generate_outputs(contexts,request.llm_model,previous,progress.tick)
        if request.series_mode=='connected' and drafts:
            for output in outputs:output['series']['title']=drafts[0]['title'].rsplit(' · ',1)[0]
        progress.done();progress.begin('editorial','ANALYZING',len(outputs),'clips')
        assessed=[]
        for i,(output,draft,ctx) in enumerate(zip(outputs,drafts,contexts)):
            output['publishing_metadata']=draft;output['title']=draft['title']
            if draft.get('thumbnail_text'):
                output['thumbnail'].update(make_thumbnail(root/output['name'],root/output['thumbnail']['name'],draft['thumbnail_text'],progress.tick))
            output['editorial']=assess(output,transcript,evidence_ranges if request.mode=='longs' else evidence_ranges[i:i+1],request,draft,assessed,request.metadata_preferences)
            assessed.append(output['editorial']);progress.tick(i+1,len(outputs))
        progress.done()
        update(result={'outputs':outputs,'publishing_state':'AWAITING_EDITORIAL_REVIEW','cache_hits':progress.cache_hits})
        from .reproducibility import record
        progress.begin('validation','RENDERING',operation='reproducibility')
        if not peaks.samples:
            peaks.sample()
        provenance_sources=sources if compiling else {'source-1':{'source':source,'metadata':metadata}}
        evidence=record(jid,timeline,provenance_sources,request,scenes,background,assets,hook_bindings,outputs,progress,peaks)
        write_json_atomic(root/'reproducibility.json',evidence,ensure_ascii=True)
        progress.done()
        update(result={'reproducibility':{'file':'reproducibility.json','timeline_sha256':evidence['timeline_sha256'],
                                         'application_commit':evidence['application_commit'],'resources':evidence['resources']}})
        metadata_obj={'job_id':jid,'request':request.model_dump(),'source':metadata,'language':transcript['language'],'candidates':candidates,'outputs':outputs}
        if request.save_drive:
            artifact_paths=[root/'transcript.json',root/'metadata.json',root/'reproducibility.json',*root.glob('timeline.json'),
                            *(p for suffix in ('.srt','.vtt','.ass','.validation.json') for p in root.glob('*'+suffix)
                              if not p.name.startswith('proxy-')),
                            *(root/o['edit_transcript'] for o in outputs if o.get('edit_transcript'))]
            total_files=sum(1+bool(o.get('thumbnail'))+int(o['name'] in raw_sources) for o in outputs)+sum(p.name=='metadata.json' or (p.is_file() and p.stat().st_size>0) for p in artifact_paths)
            progress.begin('drive','UPLOADING',total_files,'files');progress.tick(0,total_files)
            from .drive import Drive
            drive=Drive()
            try:
                folders=drive.job_folders(jid);uploaded=[]
                uploaded_files=0
                def upload_file(path,folder,key):
                    nonlocal uploaded_files
                    progress.counters['drive']['message']='Verifying '+path.name
                    def bytes_tick(current=None,total=None):update(result={'upload_asset':{'name':path.name,'current':current,'total':total}})
                    remote=drive.upload(path,folder,key,bytes_tick)
                    uploaded_files+=1;progress.tick(uploaded_files,total_files)
                    return remote
                for output in outputs:
                    remote=upload_file(root/output['name'],folders[request.mode],jid+'-'+output['name'])
                    if output.get('thumbnail'):
                        thumb=output['thumbnail']['name'];output['thumbnail']['drive']=upload_file(root/thumb,folders['thumbnails'],jid+'-'+thumb)
                    if output['name'] in raw_sources:
                        raw=raw_sources[output['name']];output['edit_source']=upload_file(raw,folders['sources'],jid+'-edit-'+output['name'])
                    uploaded.append({**output,'drive':remote});update(result={'outputs':uploaded+outputs[len(uploaded):]})
                metadata_obj['outputs']=uploaded
                write_json_atomic(root/'metadata.json',metadata_obj,ensure_ascii=True)
                artifacts={}
                for path in artifact_paths:
                    if not path.stat().st_size:continue
                    folder=folders['job'] if path.suffix=='.json' else folders['subtitles']
                    artifacts[path.name]=upload_file(path,folder,jid+'-'+path.name);update(result={'artifacts':artifacts})
                update(result={'outputs':uploaded,'artifacts':artifacts,'cloud_verified':True})
            finally:drive.close()
            progress.done();remove_workspace(root)
            if request.source.startswith('upload:'):
                original=config.SCRATCH/'uploads'/request.source[7:]
                if original.is_file() and not store.source_in_use(request.source,jid):original.unlink()
        else:
            for output in outputs:
                if output['name'] in raw_sources:output['edit_source']={'local':raw_sources[output['name']].name}
            update(result={'outputs':outputs,'previous_timeline_outputs':None})
            write_json_atomic(root/'metadata.json',metadata_obj,ensure_ascii=True);progress.done('drive','skipped','Local export selected')
        update('READY')
        if request.save_drive:
            from .retention import register
            register(store.get(jid))
    except InterruptedError:return
    except Exception as error:
        retryable = isinstance(error, media.MediaFailure) and error.retryable and stage!='UPLOADING'
        if isinstance(error, media.MediaFailure):
            code = error.code
        elif isinstance(error, NeedsReview):
            code = 'EDITORIAL_REVIEW_REQUIRED'
        elif isinstance(error, ValueError):
            code = 'INVALID_INPUT'
        else:
            code = 'STAGE_FAILED'
        safe=(str(error) if isinstance(error,(ValueError,RuntimeError,TimeoutError))
              else f'{type(error).__name__} in {stage}; inspect configuration and retry')[:500]
        failure={'code':code,'stage':progress.active or stage,'message':safe,'retryable':retryable}
        try:
            progress.done(status='failed',message=safe,error_code=code)
            state = 'QUEUED' if retryable else 'BLOCKED' if stage=='UPLOADING' or isinstance(error,NeedsReview) else 'FAILED'
            update(state,error=safe,result={'failure':failure})
        except InterruptedError:pass
    finally:
        MODEL_PROGRESS.reset(model_context)
        cancel_event.set();heartbeat.join(timeout=1)
