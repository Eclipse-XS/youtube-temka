import json
from pathlib import Path
import shutil
import sys
import threading
import re
import os
from . import config, store, media
from .models import JobRequest
from .highlights import analyze
from .resources import preflight
from .cleanup import remove_workspace


def process(claim):
    job=claim['job']
    jid=job['id']
    lease=claim['lease']
    request=JobRequest.model_validate(job['request'])
    root=config.SCRATCH/jid
    root.mkdir(parents=True,exist_ok=True)
    stage='PROBING'
    def update(state=None,**kwargs):
        nonlocal stage
        if state:
            stage=state
        store.update(jid,lease,state=state,**kwargs)
    def tick(current=None,total=None):
        update(current=current,total=total)
    stop=threading.Event()
    def renew():
        while not stop.wait(15):
            try:
                store.update(jid,lease)
            except Exception:
                return
    heartbeat=threading.Thread(target=renew,daemon=True)
    heartbeat.start()
    try:
        if job['result'].get('cloud_verified'):
            # Crash between verified upload, cleanup and READY: no re-download.
            remove_workspace(root)
            update('READY')
            return
        preflight()
        metadata=media.probe(request.source)
        end=min(request.end,metadata['duration'])
        if end<=request.start:
            raise ValueError('Selected interval begins after the end of the source')
        available=[r for r in metadata['resolutions'] if request.resolution=='best' or r<=request.resolution]
        if not available:
            raise ValueError('No source resolution at or below the selected quality is available')
        resolution=max(available)
        update(result={'source':metadata,'actual_resolution':resolution,'source_start':request.start,'processing_end':end,'ingest_strategy':'audio-first bounded chunks' if metadata.get('independent_audio',True) else 'bounded muxed segments: independent audio stream unavailable'})
        transcript_path=root/'transcript.json'
        if request.mode=='longs' and not request.captions and not transcript_path.exists():
            transcript_path.write_text(json.dumps({'language':request.language,'segments':[],'text':''}),encoding='utf-8')
        if not transcript_path.exists():
            segments=[]
            language=request.language
            for start in range(0,int(end-request.start)+1,900):
                stop=min(start+900,end-request.start)
                if stop<=start:
                    break
                partial=root/f'transcript-{start}.json'
                if not partial.exists():
                    update('DOWNLOADING')
                    audio=root/f'audio-{start}.mka'
                    media.download(request.source,audio,request.start+start,request.start+stop,resolution,True,tick)
                    update('TRANSCRIBING',current=start,total=end-request.start)
                    media.run([sys.executable,'-m','factory.transcribe',str(audio),str(partial),language or 'auto'],tick,env={**os.environ,'WHISPER_MODEL':request.asr_model or config.ASR_MODEL})
                    audio.unlink(missing_ok=True)
                part=json.loads(partial.read_text(encoding='utf-8'))
                language=language or part['language']
                for segment in part['segments']:
                    for name in ('start','end'):
                        segment[name]+=start
                    for word in segment.get('words',[]):
                        word['start']+=start
                        word['end']+=start
                    segments.append(segment)
                update('TRANSCRIBING',current=stop,total=end-request.start)
            transcript={'language':language,'segments':segments,'text':' '.join(s['text'] for s in segments)}
            from jsonfile import write_json_atomic
            write_json_atomic(transcript_path,transcript,ensure_ascii=True)
        transcript=json.loads(transcript_path.read_text(encoding='utf-8'))
        from subtitles import generate_srt
        if not generate_srt(transcript,0,end-request.start,str(root/'transcript.srt')):
            (root/'transcript.srt').write_text('',encoding='utf-8')
        srt=(root/'transcript.srt').read_text(encoding='utf-8')
        (root/'transcript.vtt').write_text('WEBVTT\n\n'+re.sub(r'(\d\d:\d\d:\d\d),(\d{3})',r'\1.\2',srt.lstrip('\ufeff')),encoding='utf-8')
        if request.mode=='longs' or request.intervals:
            intervals=request.intervals or [(request.start,end)]
            candidates=[{'start_seconds':a-request.start,'end_seconds':b-request.start,'title':metadata['title']} for a,b in sorted(intervals)]
            result={'candidates':candidates,'analysis':'manual chronological intervals'}
        else:
            update('ANALYZING')
            result=analyze(transcript,request,end-request.start,tick)
            candidates=result['candidates']
        update(result={**result,'language':transcript['language']})
        if not candidates:
            raise ValueError('No suitable highlight found within the duration bounds. Inspect the transcript or select another interval.')
        outputs=[]
        update('RENDERING')
        for i,candidate in enumerate(candidates):
            output=root/f'clip-{i+1}.mp4'
            if output.exists():
                try:
                    media.validate_output(output,candidate['end_seconds']-candidate['start_seconds'])
                except Exception:
                    output.unlink()
            if not output.exists():
                clip=root/f'selected-{i+1}.mp4'
                media.download(request.source,clip,request.start+candidate['start_seconds'],request.start+candidate['end_seconds'],resolution,False,tick)
                background=config.DATA/'backgrounds'/request.background if request.background else None
                media.render(clip,output,transcript,candidate['start_seconds'],candidate['end_seconds'],request,background,tick)
                clip.unlink(missing_ok=True)
            thumbnail=output.with_suffix('.jpg')
            if not thumbnail.exists():
                media.run([media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-i',str(output),'-frames:v','1','-vf','scale=320:-2',str(thumbnail)],tick)
            outputs.append({'name':output.name,'title':candidate['title'],'approved':False,'thumbnail':{'name':thumbnail.name}})
        if request.mode=='longs' and len(outputs)>1:
            final=root/'long.mp4'
            media.concatenate([root/o['name'] for o in outputs],final,tick)
            outputs=[{'name':final.name,'title':metadata['title'],'approved':False}]
        update(result={'outputs':outputs})
        metadata_obj={'job_id':jid,'request':request.model_dump(),'source':metadata,'language':transcript['language'],'candidates':candidates,'outputs':outputs}
        (root/'metadata.json').write_text(json.dumps(metadata_obj,ensure_ascii=False,sort_keys=True),encoding='utf-8')
        if request.save_drive:
            update('UPLOADING')
            from .drive import Drive
            drive=Drive()
            try:
                folders=drive.job_folders(jid)
                uploaded=[]
                for output in outputs:
                    remote=drive.upload(root/output['name'],folders[request.mode],jid+'-'+output['name'],tick)
                    if output.get('thumbnail'):
                        thumb=output['thumbnail']['name']
                        output['thumbnail']['drive']=drive.upload(root/thumb,folders['thumbnails'],jid+'-'+thumb,tick)
                    uploaded.append({**output,'drive':remote})
                    update(result={'outputs':uploaded+outputs[len(uploaded):]})
                metadata_obj['outputs']=uploaded
                (root/'metadata.json').write_text(json.dumps(metadata_obj,ensure_ascii=False,sort_keys=True),encoding='utf-8')
                artifacts={}
                for path in [transcript_path,root/'metadata.json',*root.glob('*.srt'),*root.glob('*.vtt'),*root.glob('*.ass')]:
                    if path.stat().st_size==0:
                        continue
                    folder=folders['job'] if path.suffix=='.json' else folders['subtitles']
                    artifacts[path.name]=drive.upload(path,folder,jid+'-'+path.name,tick)
                    update(result={'artifacts':artifacts})
                update(result={'outputs':uploaded,'artifacts':artifacts,'cloud_verified':True})
            finally:
                drive.close()
            # No removal before every required artifact has been verified.
            remove_workspace(root)
            source=media.local_source(request.source)
            if source:
                # Preserve sources referenced by any other job.
                others=[j for j in store.list_jobs() if j['id']!=jid and j['request']['source']==request.source and j['state'] not in ('READY','CANCELLED')]
                if not others:
                    source.unlink(missing_ok=True)
        update('READY')
    except InterruptedError:
        return
    except Exception as error:
        # Never serialize raw third-party exception bodies (OAuth/URLs).
        safe=str(error) if isinstance(error,(ValueError,RuntimeError,TimeoutError)) else f'{type(error).__name__} in {stage}; inspect configuration and retry'
        try:
            update('BLOCKED' if stage=='UPLOADING' else 'FAILED',error=safe[:500])
        except InterruptedError:
            pass
    finally:
        stop.set()
        heartbeat.join(timeout=1)
