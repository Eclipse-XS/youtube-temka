"""Bounded ingest and rendering, using OpenShorts caption/encoder modules."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import signal
import textwrap
from collections import deque
from urllib.parse import urlsplit
from . import config
from .resources import preflight
from jsonfile import write_json_atomic


class MediaFailure(RuntimeError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def ffmpeg():
    if os.environ.get('FFMPEG_BINARY'):
        return os.environ['FFMPEG_BINARY']
    if shutil.which('ffmpeg'):
        return shutil.which('ffmpeg')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args, tick=lambda *_:None, duration=None, timeout=7200, env=None, cwd=None):
    group={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,cwd=cwd,**group)
    # Backpressure bounds logs even if a child is noisy or progress persistence
    # is slow. readline's size also bounds a child that never writes a newline.
    lines=queue.Queue(maxsize=128)
    stopped=threading.Event()
    def enqueue(line):
        while not stopped.is_set():
            try:
                lines.put(line,timeout=.1)
                return True
            except queue.Full:pass
        return False
    def read():
        try:
            while not stopped.is_set():
                line=process.stdout.readline(4096)
                if not line or not enqueue(line):break
        finally:enqueue(None)
    thread=threading.Thread(target=read,daemon=True)
    thread.start()
    started=time.monotonic()
    tail=deque(maxlen=12)
    next_check=0.0
    next_quota_check=0.0
    progress=None
    eof=False
    try:
        while True:
            now=time.monotonic()
            if now-started > timeout:
                raise MediaFailure('MEDIA_TIMEOUT', 'Media operation timed out; check the source connection or shorten the interval.', True)
            if now>=next_check:
                if now>=next_quota_check:
                    preflight()
                    next_quota_check=now+3
                elif config.RESERVE_BYTES and shutil.disk_usage(config.SCRATCH).free < config.RESERVE_BYTES:
                    raise RuntimeError('Free-space reserve would be exceeded. Free disk space before retrying.')
                tick(progress,duration)
                next_check=now+.5
            if eof:
                if process.poll() is not None:break
                time.sleep(.1)
                continue
            try:
                line=lines.get(timeout=.25)
            except queue.Empty:
                continue
            if line is None:
                eof=True
                continue
            tail.append(line)
            if line.startswith('out_time_us='):
                try:
                    progress=float(line.split('=')[1])/1e6
                except ValueError:
                    pass
            elif 'Transcribing' in line and duration:
                import re
                measured=re.search(r'Transcribing.*?(\d+)%',line)
                if measured:progress=min(100,int(measured[1]))/100*duration
        if process.returncode != 0:
            # Do not return raw downloader logs: URLs may carry credentials.
            diagnostic=' '.join(tail).casefold()
            code='MEDIA_PROCESS_FAILED';retryable=False
            if any(value in diagnostic for value in ('cuda out of memory','cuda_error_out_of_memory')):
                code,reason='GPU_MEMORY', 'GPU memory exhausted; use a smaller model or wait for GPU memory to be released'
            elif 'out of memory' in diagnostic or 'cannot allocate memory' in diagnostic:
                code,reason='SYSTEM_MEMORY', 'System/container memory exhausted; shorten the chunk or choose a smaller model'
            elif 'no space left on device' in diagnostic:
                code,reason='DISK_SPACE', 'Disk space exhausted; free scratch storage and retry'
            elif any(value in diagnostic for value in ('http error 429','429 too many requests','server returned 429')):
                code,reason,retryable='DOWNLOAD_RATE_LIMITED','Source rate limited the request; wait before retrying',True
            elif any(value in diagnostic for value in ('connection timed out','connection reset','temporarily unavailable','http error 503','server returned 5')):
                code,reason,retryable='SOURCE_UNAVAILABLE','Source connection was interrupted; verify the connection if retries fail',True
            elif any(value in diagnostic for value in ('downloaded range is empty', 'downloaded range is not decodable', 'downloaded range contains no decodable media')):
                code,reason,retryable='SOURCE_RANGE_INCOMPLETE','Source interval returned empty or incomplete media; check VOD availability',True
            elif process.returncode in (-9,137):
                code,reason='MEDIA_PROCESS_KILLED','Process killed; inspect container OOM diagnostics and available RAM before retrying'
            else:
                reason='Check codec support, source accessibility and available disk space'
            raise MediaFailure(code, f'Media process failed (exit {process.returncode}). {reason}. Checkpoints preserved.', retryable)
        if progress is not None:
            tick(progress,duration)
    finally:
        stopped.set()
        if process.poll() is None:
            if os.name=='nt':
                try:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
                except subprocess.TimeoutExpired:pass
                # Restricted Windows sessions may reject taskkill. Still reap
                # the direct child rather than waiting forever after cancellation.
                if process.poll() is None:process.kill()
            else:
                os.killpg(process.pid,signal.SIGKILL)
        process.wait()
        thread.join(timeout=2)
        if not thread.is_alive():process.stdout.close()


def local_source(source):
    if source.startswith('job-local:'):
        import re
        jid=source.split(':',1)[1]
        if not re.fullmatch('[a-f0-9]{32}',jid):raise ValueError('Invalid editable source')
        return config.SCRATCH/jid/'edit-source.mp4'
    if source.startswith('upload:'):
        name=source[7:]
        if not name or Path(name).name != name:
            raise ValueError('Invalid uploaded source identifier')
        path=config.SCRATCH/'uploads'/name
        if not path.is_file():
            raise ValueError('Uploaded source is missing')
        return path
    return None


def fetch_drive(metadata,path,tick=lambda *_:None):
    import hashlib
    from .drive import Drive,BASE,CHUNK
    if path.is_file():
        with path.open('rb') as source:
            if hashlib.file_digest(source,'md5').hexdigest()==metadata['md5Checksum']:return path
    preflight(int(metadata['size']))
    drive=Drive()
    try:
        offset=0;total=int(metadata['size'])
        with path.open('wb') as output:
            while offset<total:
                end=min(total,offset+CHUNK)-1
                with drive.client.stream('GET',BASE+'/files/'+metadata['id'],params={'alt':'media','supportsAllDrives':'true'},headers={'Range':f'bytes={offset}-{end}'}) as response:
                    if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {offset}-{end}/{total}':raise ValueError('Drive did not honor bounded editable-source retrieval')
                    count=0
                    for data in response.iter_bytes(256*1024):
                        count+=len(data)
                        if count>end-offset+1:raise ValueError('Drive response exceeded the requested range')
                        preflight(len(data));output.write(data)
                    if count!=end-offset+1:raise ValueError('Incomplete editable-source transfer; retry safely')
                offset=end+1;tick(offset,total)
        with path.open('rb') as source:
            if hashlib.file_digest(source,'md5').hexdigest()!=metadata['md5Checksum']:raise ValueError('Editable source checksum mismatch')
    finally:drive.close()
    return path


def validate_url(url):
    host=urlsplit(url).hostname or ''
    allowed=('youtube.com','youtu.be','twitch.tv')
    if urlsplit(url).scheme != 'https' or not any(host==h or host.endswith('.'+h) for h in allowed) or urlsplit(url).username:
        raise ValueError('Use an HTTPS YouTube/completed Twitch VOD URL or upload an MP4/MKV/MOV')
    from security_utils import assert_public_url
    assert_public_url(url)


def probe(source):
    path=local_source(source)
    if path:
        import av
        with av.open(str(path)) as c:
            video=next(iter(c.streams.video),None)
            if video is None or c.duration is None:
                raise ValueError('Source must have a video stream and known duration')
            return {'title':path.stem,'platform':'local','duration':c.duration/av.time_base,'resolutions':[video.height],'size':path.stat().st_size,'has_audio':bool(c.streams.audio)}
    validate_url(source)
    import yt_dlp
    import ssrf_guard
    try:
        with ssrf_guard.guarded(), yt_dlp.YoutubeDL({'quiet':True,'noplaylist':True,'socket_timeout':20,'skip_download':True}) as ydl:
            item=ydl.extract_info(source,download=False)
    except yt_dlp.utils.DownloadError as error:
        detail=str(error).casefold()
        if '429' in detail and ('http' in detail or 'too many requests' in detail):
            raise MediaFailure('DOWNLOAD_RATE_LIMITED','Source rate limited the request; wait before retrying.',True) from None
        if any(word in detail for word in ('timed out','connection reset','http error 503')):
            raise MediaFailure('SOURCE_UNAVAILABLE','Could not reach the source. Check the connection.',True) from None
        raise MediaFailure('SOURCE_ACCESS_FAILED','Could not access the media. Verify the URL, privacy and source availability.') from None
    if item.get('is_live') or item.get('live_status') in ('is_live','is_upcoming'):
        raise ValueError('Only completed VODs are supported')
    if not item.get('duration'):
        raise ValueError('Unknown source duration; bounded processing cannot be guaranteed')
    formats=item.get('formats',[])
    return {'title':item.get('title'),'platform':item.get('extractor_key'),'duration':item['duration'],'resolutions':sorted({int(f['height']) for f in formats if f.get('height') and f.get('vcodec') not in ('none',None,'images') and f.get('ext')!='mhtml'}),'size':item.get('filesize'),'thumbnail':item.get('thumbnail'),'has_audio':any(f.get('acodec') not in ('none',None) for f in formats),'independent_audio':any(f.get('vcodec')=='none' and f.get('acodec') not in ('none',None) for f in formats)}


def download(source,path,start,end,resolution,audio=False,tick=lambda *_:None):
    """Never fall back to downloading the full remote VOD."""
    preflight()
    local=local_source(source)
    if local:
        args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-threads','2','-ss',str(start),'-i',str(local),'-t',str(end-start),'-threads','2','-filter_threads','1']
        if audio:
            args+=['-vn','-ac','1','-ar','16000','-c:a','pcm_s16le']
        else:
            args+=['-vf',f'scale=-2:min(ih\\,{resolution})','-c:v','libx264','-preset','fast','-c:a','aac']
        run(args+['-progress','pipe:1',str(path)],tick,end-start)
        return path
    validate_url(source)
    # yt-dlp's range downloader uses remote FFmpeg seeking. No unbounded retry.
    # A separate process allows the parent to enforce scratch/lease/time limits.
    import sys
    fmt='bestaudio/best' if audio else f'bv*[height<={resolution}]+ba/b[height<={resolution}]'
    args=[sys.executable,'-m','factory.range_download',source,str(path),str(start),str(end),fmt,ffmpeg()]
    run(args,tick,end-start)
    return path


def render(source,output,transcript,start,end,request,background=None,tick=lambda *_:None,stage=None,music_path=None,logo_path=None,
           timeline_sounds=(),force_audio=False,transition_seconds=None,timeline_effects=(),asset_paths=None,caption_cues=None,
           preview=False):
    from .heavy import HEAVY_LOCK
    with HEAVY_LOCK:
        return _render(source,output,transcript,start,end,request,background,tick,stage,music_path,logo_path,
                       timeline_sounds,force_audio,transition_seconds,timeline_effects,asset_paths,caption_cues,preview)


def _render(source,output,transcript,start,end,request,background=None,tick=lambda *_:None,stage=None,music_path=None,logo_path=None,
            timeline_sounds=(),force_audio=False,transition_seconds=None,timeline_effects=(),asset_paths=None,caption_cues=None,
            preview=False):
    from subtitles import generate_ass, generate_srt
    from ffmpeg_utils import DELIVERY, QUALITY, video_encode_args, escape_filter_value, LOUDNORM_FILTER
    from .captions import appearance
    from .timeline_filters import audio_graph, font_option, playback_graph, playback_ranges, retime_transcript, visual_graph
    # Loudnorm alone can overshoot after AAC encoding, especially for transient
    # synthetic speech. Limit at the final sample rate with makeup gain disabled.
    audio_filter=f'{LOUDNORM_FILTER},aformat=sample_rates=48000:channel_layouts=stereo,alimiter=limit=0.707945:level=false:latency=true'
    duration=end-start
    transcript={
        'language':transcript.get('language'),
        'segments':[segment for segment in transcript['segments']
                    if segment['end']>start and segment['start']<end],
    }
    import av
    with av.open(str(source)) as container:
        has_audio=bool(container.streams.audio)
    if stage:stage('captions_audio')
    if request.silence_removal and request.audio_mode!='voiceover':
        from .audio_edit import remove_pauses
        source,transcript,start,end=remove_pauses(source,output.with_suffix('.trimmed.mp4'),transcript,start,end,has_audio,tick)
        duration=end-start
    playback=playback_ranges(timeline_effects,duration)
    if playback:
        transcript=retime_transcript(transcript,playback,start)
    narration=None
    caption_start,caption_end=start,end
    if request.audio_mode=='voiceover':
        from .tts import synthesize
        text=request.tts_text or ' '.join(s['text'] for s in transcript['segments'] if s['end']>start and s['start']<end)
        narration=output.with_suffix('.voice.wav')
        synthesize(text,request.tts_voice,request.tts_speed,transcript.get('language') or request.language or 'en',narration,tick)
        with av.open(str(narration)) as audio_container:
            voice_duration=audio_container.duration/av.time_base
        if voice_duration>duration+.1:
            raise ValueError('Voice-over is longer than the clip. Shorten its text or select a longer interval; words were not truncated.')
        if request.captions and caption_cues is None:
            import sys
            timed=output.with_suffix('.voice.json')
            run([sys.executable,'-m','factory.transcribe',str(narration),str(timed),transcript.get('language') or request.language or 'en'],tick)
            transcript=json.loads(timed.read_text(encoding='utf-8'))
            caption_start,caption_end=0,duration
    ass=output.with_suffix('.ass')
    srt=output.with_suffix('.srt')
    if caption_cues is not None:
        transcript={'language':transcript.get('language'),'segments':caption_cues}
        caption_start,caption_end=0,duration
    elif request.captions and request.subtitle_language and transcript.get('language')!=request.subtitle_language:
        from .captions import translate
        translated=output.with_suffix('.translated.json')
        if translated.is_file():transcript=json.loads(translated.read_text(encoding='utf-8'))
        else:
            transcript=translate(transcript,request.subtitle_language,request.llm_model)
            write_json_atomic(translated,transcript,ensure_ascii=True)
    generate_srt(transcript,caption_start,caption_end,str(srt),preserve_cues=caption_cues is not None)
    generate_ass(transcript,caption_start,caption_end,str(ass),preserve_cues=caption_cues is not None,**appearance(request))
    # Source is already a precisely extracted selected interval.
    args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-threads','2','-i',str(source)]
    width,height=delivery_dimensions(request,preview)
    scale=height/delivery_dimensions(request)[1]
    preset=request.preset
    framing={'strategy':preset}
    if preset=='auto':preset='gameplay' if background and background.is_file() else 'smart'
    trajectory=None
    if request.mode=='shorts' and preset=='smart':
        from .framing import trajectory as track,dedupe_sendcmd_lines
        trajectory,framing=track(source,duration)
        if trajectory:
            crop_w,crop_h,positions=trajectory
            commands=output.with_suffix('.camera.txt')
            commands.write_text('\n'.join(dedupe_sendcmd_lines(positions,2)),encoding='utf-8')
        else:preset='blur'
    playback_parts,video_input,audio_input=playback_graph(playback,has_audio)
    if playback and has_audio and request.audio_mode in ('silent','voiceover'):
        playback_parts.append(f'{audio_input}anullsink')
    if request.mode=='longs':
        graph=f'{video_input}scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]'
    elif preset=='gameplay':
        if not background or not background.is_file():
            raise ValueError('Gameplay requires an authorized background asset; choose Blur or upload an asset')
        args+=['-stream_loop','-1','-threads','2','-i',str(background)]
        top=2*round(height*request.split_ratio/2)
        bottom=height-top
        graph=f'{video_input}scale={width}:{top}:force_original_aspect_ratio=increase,crop={width}:{top},setsar=1[top];[1:v]scale={width}:{bottom}:force_original_aspect_ratio=increase,crop={width}:{bottom},setsar=1[bottom];[top][bottom]vstack[v]'
    elif preset=='smart' and trajectory:
        graph=f"{video_input}sendcmd=f='{escape_filter_value(str(commands.resolve()))}',crop@c={crop_w}:{crop_h}:{positions[0]}:0,scale={width}:{height},setsar=1[v]"
    elif preset=='crop':
        # Explicit center framing fallback; no unverified face-tracking claim.
        graph=f'{video_input}scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1[v]'
    else:
        graph=f'{video_input}split[a][b];[a]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur={max(1,round(20*scale))}:2[bg];[b]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]'
    next_input=2 if preset=='gameplay' and request.mode=='shorts' else 1
    visual_parts,video,next_input=visual_graph(timeline_effects,args,'[v]',next_input,width,height,output,asset_paths)
    graph=';'.join([*playback_parts,graph,*visual_parts])
    if request.captions and ass.exists():
        graph+=f";{video}ass=filename='{escape_filter_value(str(ass.resolve()))}'[captioned]"
        video='[captioned]'
    if request.hook:
        hookfile=output.with_suffix('.hook.txt')
        fontsize=round(request.hook_font_size*scale)
        minimum_size=max(6,round(18*scale))
        if request.hook_wrap:
            while True:
                hooklines=textwrap.wrap(request.hook,width=max(1,min(26,int(width*.84/(fontsize*1.1)))))
                if len(hooklines)*fontsize*1.2<=height*.55 or fontsize<=minimum_size:break
                fontsize-=max(1,round(2*scale))
            text='\n'.join(hooklines)
        else:
            text=request.hook
        hookfile.write_text(text,encoding='utf-8',newline='')
        # Windows FFmpeg builds may have no fontconfig configuration. An explicit
        # installed font avoids drawtext terminating the entire render process.
        font=font_option(request.hook_font)
        anchor={'top':'h*0.12','center':'(h-th)/2','bottom':'h*0.75-th'}[request.hook_position]
        x=f'clip((w-tw)/2+{round(request.hook_x*scale)},w*.05,max(w*.05,w*.95-tw))'
        y=f'clip({anchor}+{round(request.hook_y*scale)},h*.05,max(h*.05,h*.95-th))'
        show=f'gte(t,{request.hook_start})'
        if not request.hook_pinned:
            show+=f'*lt(t,{request.hook_start+request.hook_duration})'
        shadow=round(2*scale) if request.hook_shadow else 0
        graph+=(f";{video}drawtext={font}textfile='{escape_filter_value(str(hookfile.resolve()))}':expansion=none:"
                f"fontcolor={request.hook_color}:fontsize={fontsize}:borderw={round(request.hook_outline*scale)}:bordercolor=black:"
                f"shadowx={shadow}:shadowy={shadow}:box={int(request.hook_box)}:boxcolor=black@{request.hook_box_opacity}:"
                f"boxborderw={round(request.hook_padding*scale)}:x='{x}':y='{y}':enable='{show}'[hooked]")
        video='[hooked]'
    audio_map=None
    if request.logo_asset:
        logo=logo_path or config.DATA/'logos'/request.logo_asset
        if not logo.is_file():raise ValueError('Selected logo is unavailable')
        args+=['-threads','1','-i',str(logo)]
        margin=round(32*scale)
        graph+=f';[{next_input}:v]scale={max(margin,width//8)}:{max(margin,height//8)}:force_original_aspect_ratio=decrease[logo];{video}[logo]overlay=W-w-{margin}:{margin}[branded]'
        video='[branded]';next_input+=1
    if request.cta_text:
        cta_size=round(32*scale)
        ctafile=output.with_suffix('.cta.txt');ctafile.write_text('\n'.join(textwrap.wrap(request.cta_text,width=max(1,int(width*.84/(cta_size*1.1))))),encoding='utf-8')
        ctafont=''
        if os.name=='nt':
            ctafontpath=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf'
            if ctafontpath.is_file():ctafont=f"fontfile='{escape_filter_value(str(ctafontpath.resolve()))}':"
        graph+=f";{video}drawtext={ctafont}textfile='{escape_filter_value(str(ctafile.resolve()))}':expansion=none:fontcolor=white:fontsize={cta_size}:box=1:boxcolor=black@0.65:boxborderw={round(10*scale)}:x=(w-tw)/2:y=h*0.8-th:enable='gte(t,{max(0,duration-4)})'[cta]"
        video='[cta]'
    music=music_path or (config.DATA/'music'/request.music_asset if request.music_asset else None)
    if request.audio_mode=='music' and music and not music.is_file():raise ValueError('Selected music asset is missing; choose an available authorized asset')
    if request.audio_mode=='voiceover':
        args+=['-i',str(narration)]
        graph+=f';[{next_input}:a]apad,atrim=duration={duration},{audio_filter}[audio]'
        audio_map='[audio]'
    elif request.audio_mode=='music' and music and music.is_file():
        args+=['-stream_loop','-1','-i',str(music)]
        graph+=f';[{next_input}:a]atrim=duration={duration},afade=t=in:d=0.3,afade=t=out:st={max(0,duration-.5)}:d=0.5,volume=0.12[bed]'
        if has_audio:
            graph+=f';{audio_input}asplit[original][side];[bed][side]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[duck];[original][duck]amix=inputs=2:normalize=0,{audio_filter}[audio]'
        else:graph+=f';[bed]{audio_filter}[audio]'
        audio_map='[audio]'
    elif has_audio and request.audio_mode!='silent':
        graph+=f';{audio_input}{audio_filter}[audio]';audio_map='[audio]'
    if audio_map:
        audio_parts,audio_map=audio_graph(timeline_effects,audio_map)
        if audio_parts:
            graph+=';'+';'.join(audio_parts)
    if timeline_sounds or force_audio:
        from .audio_edit import PROCEDURAL_SOUNDS

        if not audio_map:
            graph+=';anullsrc=r=48000:cl=stereo[silence]'
            audio_map='[silence]'
        mixed=[audio_map]
        for index,sound in enumerate(timeline_sounds):
            milliseconds,expression=PROCEDURAL_SOUNDS[sound.kind]
            length=milliseconds/1000
            label=f'[sfx{index}]'
            graph+=(f";aevalsrc='{expression}':s=48000:d={length},"
                    f'aformat=channel_layouts=stereo,volume={sound.gain},'
                    f'adelay={round(sound.start*1000)}:all=1{label}')
            mixed.append(label)
        if len(mixed)>1:
            graph+=(';' + ''.join(mixed) + f'amix=inputs={len(mixed)}:normalize=0,'
                    'alimiter=limit=0.707945:level=false:latency=true[mixed]')
            audio_map='[mixed]'
    if request.transition=='fade':
        fade_duration=min(.25,duration/4) if transition_seconds is None else min(transition_seconds,duration/2)
        fade_end=duration-fade_duration
        graph+=f';{video}fade=t=in:d={fade_duration},fade=t=out:st={fade_end}:d={fade_duration}[faded]'
        video='[faded]'
        if audio_map:
            graph+=f';{audio_map}afade=t=in:d={fade_duration},afade=t=out:st={fade_end}:d={fade_duration}[faded_audio]'
            audio_map='[faded_audio]'
    args+=['-filter_complex_threads','1','-filter_complex',graph,'-map',video]
    args+=['-map',audio_map,'-c:a','aac','-b:a','192k','-ar','48000'] if audio_map else ['-an']
    encoding=video_encode_args(DELIVERY if preview else QUALITY)
    bitrate=min(request.bitrate,1_800_000) if preview else request.bitrate
    args+=[*encoding,'-maxrate',str(bitrate),'-bufsize',str(bitrate*2),'-threads','2','-pix_fmt','yuv420p']
    if preview or not request.preserve_fps:
        args+=['-r','30']
    temporary=output.with_suffix('.rendering.mp4')
    args+=['-t',str(duration),'-movflags','+faststart','-progress','pipe:1',str(temporary)]
    if stage:stage('rendering',encoder=encoding[1])
    try:
        run(args,tick,duration)
        if stage:stage('validation')
        report=validate_output(temporary,duration,request=request,expected_audio=audio_map is not None,preview=preview)
        temporary.replace(output)
    finally:temporary.unlink(missing_ok=True)
    write_json_atomic(output.with_suffix('.validation.json'),{**report,'framing':framing,
                      'media_fingerprint':media_fingerprint(output,request,preview=preview)})
    return output


def delivery_dimensions(request, preview=False):
    if request.mode=='shorts':
        return (540,960) if preview else (1080,1920)
    height=360 if preview else request.output_height
    return height*16//9//2*2,height


def media_fingerprint(path,request=None,*,preview=False):
    with path.open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    profile=[request.mode,request.output_height,request.destination,config.SHORTS_MAX_SECONDS] if request else None
    if preview and profile:
        profile.append('preview')
    return {'sha256':digest,'validation_version':1,'profile':profile}


def verify_checkpoint(path,report,request,*,preview=False):
    fingerprint=media_fingerprint(path,request,preview=preview)
    if report.get('validated') is True and report.get('media_fingerprint')==fingerprint:
        return report
    refreshed=validate_output(path,report['duration'],request=request,expected_audio=report.get('audio'),preview=preview)
    return {**report,**refreshed,'media_fingerprint':fingerprint}


def validate_output(path,duration,request=None,expected_audio=None,*,preview=False):
    import av
    with av.open(str(path)) as container:
        if not container.streams.video or not container.duration or abs(container.duration/av.time_base-duration)>1:
            raise RuntimeError('Rendered video validation failed (stream/duration)')
        stream=container.streams.video[0]
        stream.thread_count=2
        if request:
            expected=delivery_dimensions(request,preview)
            if (stream.width,stream.height)!=expected:raise RuntimeError('Rendered resolution/aspect ratio does not match the requested output')
            if request.destination=='youtube_shorts' and container.duration/av.time_base>config.SHORTS_MAX_SECONDS:
                raise RuntimeError(f'Rendered output exceeds the {config.SHORTS_MAX_SECONDS}s YouTube Shorts limit')
        if expected_audio is not None and bool(container.streams.audio)!=expected_audio:
            raise RuntimeError('Rendered audio track does not match the selected audio mode')
        frames=0;black_samples=0;sampled_frames=0;video_end=None
        try:
            for frame in container.decode(video=0):
                if frame.pts is not None:video_end=float(frame.pts*frame.time_base)+1/float(stream.average_rate or 30)
                if frames % max(1,round(float(stream.average_rate or 30)))==0:
                    pixels=frame.reformat(width=64,height=64,format='gray').to_ndarray()
                    sampled_frames+=1;black_samples+=int((pixels<16).mean()>.95)
                frames+=1
        except Exception:
            raise RuntimeError('Rendered container has a corrupted video packet') from None
        if not frames:
            raise RuntimeError('Rendered video has no decodable frame')
        report={'duration':container.duration/av.time_base,'width':stream.width,'height':stream.height,'frames_decoded':frames,'audio':bool(container.streams.audio),'validated':True,'black_frame_fraction':black_samples/sampled_frames,'black_frames_sampled':sampled_frames,'video_end_seconds':video_end}
    if report['audio']:
        import numpy as np
        peak=0.;samples=clipped=silent=0;audio_end=None
        with av.open(str(path)) as container:
            try:
                for frame in container.decode(audio=0):
                    if frame.pts is not None:audio_end=float(frame.pts*frame.time_base)+frame.samples/frame.sample_rate
                    values=frame.to_ndarray()
                    scale=max(abs(np.iinfo(values.dtype).min),np.iinfo(values.dtype).max) if np.issubdtype(values.dtype,np.integer) else 1
                    values=values.astype(np.float32)/scale
                    peak=max(peak,float(np.abs(values).max()));samples+=values.size
                    clipped+=int((np.abs(values)>=.9999).sum())
                    if float(np.sqrt(np.mean(values**2)))<.001:silent+=values.size
            except Exception:
                raise RuntimeError('Rendered container has a corrupted audio packet') from None
        if not samples:raise RuntimeError('Rendered audio has no decodable samples')
        report.update(audio_peak=peak,audio_clipped_fraction=clipped/samples,audio_silence_fraction=silent/samples,audio_samples_decoded=samples,audio_silence_threshold_db=-60)
        if video_end is not None and audio_end is not None:
            delta=abs(video_end-audio_end);report['audio_video_end_delta_seconds']=delta
            if delta>.25:raise RuntimeError('Rendered audio/video duration differs by more than 250 ms; inspect synchronization')
    return report


def concatenate(paths,output,tick=lambda *_:None):
    # Only application-generated file paths, never source-supplied strings.
    manifest=output.with_suffix('.concat.txt')
    manifest.write_text(''.join("file '"+p.name+"'\n" for p in paths),encoding='utf-8')
    temporary=output.with_suffix('.assembling.mp4')
    try:
        run([ffmpeg(),'-y','-hide_banner','-loglevel','error','-f','concat','-safe','1','-i',manifest.name,
             '-c','copy','-movflags','+faststart',temporary.name],tick,cwd=output.parent)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def render_card(output, card, request, tick=lambda *_:None, *, preview=False):
    from ffmpeg_utils import DELIVERY, QUALITY, escape_filter_value, video_encode_args
    from .timeline_filters import font_option

    width,height=delivery_dimensions(request,preview)
    duration = (card.end_ms - card.start_ms) / 1000
    size = height // 12
    spec = card.settings
    title = output.with_suffix('.txt')
    title.write_text('\n'.join(textwrap.wrap(spec.title, width=32)), encoding='utf-8', newline='')
    enter = min(.4, duration / 3)
    offset = f'+w*.15*max(0,1-t/{enter})' if spec.animation == 'slide' else ''
    graph = (f"drawtext={font_option(spec.font)}textfile='{escape_filter_value(str(title.resolve()))}':"
             f"expansion=none:fontcolor={spec.foreground}:fontsize={size}:line_spacing=10:"
             f"x='(w-tw)/2{offset}':y='(h-th)/2',fade=t=in:d={enter},"
             f"fade=t=out:st={duration - enter}:d={enter}")
    temporary = output.with_suffix('.rendering.mp4')
    args = [ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
            '-i', f'color=c=0x{spec.background[1:]}:s={width}x{height}:r=30', '-vf', graph,
            '-t', str(duration), '-an', *video_encode_args(DELIVERY if preview else QUALITY), '-pix_fmt', 'yuv420p',
            '-threads', '2', '-progress', 'pipe:1', str(temporary)]
    try:
        run(args, tick, duration)
        validate_output(temporary, duration, request=request, expected_audio=False,preview=preview)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def assemble_timeline(paths, output, scenes, request, tick=lambda *_:None, *, reencode=False, preview=False):
    if not reencode and not any(scene.overlap_ms for scene in scenes):
        return concatenate(paths, output, tick)

    import av
    from ffmpeg_utils import DELIVERY, QUALITY, video_encode_args

    width,height=delivery_dimensions(request,preview)
    args = [ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error']
    audio = []
    for path in paths:
        args.extend(['-threads', '2', '-i', str(path)])
        with av.open(str(path)) as container:
            audio.append(bool(container.streams.audio))
    with_audio = any(audio)
    graph = []
    for i, scene in enumerate(scenes):
        duration = (scene.end_ms - scene.start_ms) / 1000
        graph.append(f'[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,'
                     f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,'
                     f'tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration},'
                     f'setpts=PTS-STARTPTS,fps=30,settb=AVTB[v{i}]')
        if with_audio:
            source = f'[{i}:a]apad' if audio[i] else 'anullsrc=r=48000:cl=stereo'
            graph.append(f'{source},aformat=sample_rates=48000:channel_layouts=stereo,'
                         f'atrim=duration={duration},asetpts=PTS-STARTPTS[a{i}]')
    video, sound = '[v0]', '[a0]'
    for i, scene in enumerate(scenes[1:], 1):
        video_out, sound_out = f'[outv{i}]', f'[outa{i}]'
        if scene.overlap_ms:
            overlap = scene.overlap_ms / 1000
            graph.append(f'{video}[v{i}]xfade=transition=fade:duration={overlap}:offset={scene.start_ms/1000},'
                         f'fps=30,settb=AVTB{video_out}')
            if with_audio:
                graph.append(f'{sound}[a{i}]acrossfade=d={overlap}{sound_out}')
        else:
            graph.append(f'{video}[v{i}]concat=n=2:v=1:a=0,fps=30,settb=AVTB{video_out}')
            if with_audio:
                graph.append(f'{sound}[a{i}]concat=n=2:v=0:a=1{sound_out}')
        video, sound = video_out, sound_out
    duration = scenes[-1].end_ms / 1000
    temporary = output.with_suffix('.assembling.mp4')
    args.extend(['-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', video])
    if with_audio:
        args.extend(['-map', sound, '-c:a', 'aac', '-b:a', '192k'])
    bitrate=min(request.bitrate,1_800_000) if preview else request.bitrate
    args.extend([*video_encode_args(DELIVERY if preview else QUALITY), '-threads', '2', '-pix_fmt', 'yuv420p', '-t', str(duration),
                 '-maxrate', str(bitrate), '-bufsize', str(bitrate * 2),
                 '-movflags', '+faststart', '-progress', 'pipe:1', str(temporary)])
    try:
        run(args, tick, duration)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def normalize_compilation(source,output,duration,height,tick,*,start=0,input_height=None):
    """Make stream-copy assembly safe across source dimensions, frame rates and audio layouts."""
    import av
    from ffmpeg_utils import DELIVERY, video_encode_args

    width=height*16//9//2*2
    with av.open(str(source)) as container:
        has_audio=bool(container.streams.audio)
    args=[ffmpeg(),'-y','-hide_banner','-loglevel','error','-threads','2','-ss',str(start),'-i',str(source)]
    if not has_audio:
        args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
    scaling = f'scale=-2:min(ih\\,{input_height}),' if input_height else ''
    scaling += f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    args+=['-map','0:v:0','-map','0:a:0' if has_audio else '1:a:0',
           '-vf',scaling,'-af','apad','-t',str(duration),'-r','30',*video_encode_args(DELIVERY),
           '-threads','2','-filter_threads','1','-pix_fmt','yuv420p','-c:a','aac',
           '-ac','2','-ar','48000','-movflags','+faststart','-progress','pipe:1']
    temporary=output.with_suffix('.normalizing.mp4')
    try:
        run([*args,str(temporary)],tick,duration)
        validate_output(temporary,duration,expected_audio=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
