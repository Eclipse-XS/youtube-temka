"""Bounded ingest and rendering, using OpenShorts caption/encoder modules."""
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
from urllib.parse import urlsplit
from . import config
from .resources import preflight


def ffmpeg():
    if os.environ.get('FFMPEG_BINARY'):
        return os.environ['FFMPEG_BINARY']
    if shutil.which('ffmpeg'):
        return shutil.which('ffmpeg')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args, tick=lambda *_:None, duration=None, timeout=7200, env=None):
    group={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,**group)
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
    try:
        while True:
            preflight()
            tick(None,duration)
            if time.monotonic()-started > timeout:
                raise TimeoutError('Media operation timed out; shorten the interval and retry')
            try:
                line=lines.get(timeout=.25)
            except queue.Empty:
                continue
            if line is None:
                break
            if line.startswith('out_time_us='):
                try:
                    tick(float(line.split('=')[1])/1e6,duration)
                except ValueError:
                    pass
            elif 'Transcribing' in line and duration:
                import re
                measured=re.search(r'Transcribing.*?(\d+)%',line)
                if measured:tick(min(100,int(measured[1]))/100*duration,duration)
        if process.wait() != 0:
            # Do not return raw downloader logs: URLs may carry credentials.
            raise RuntimeError('Media process failed. Check codec support, source accessibility and available disk space.')
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
    with ssrf_guard.guarded(), yt_dlp.YoutubeDL({'quiet':True,'noplaylist':True,'socket_timeout':20,'skip_download':True}) as ydl:
        item=ydl.extract_info(source,download=False)
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


def render(source,output,transcript,start,end,request,background=None,tick=lambda *_:None,stage=None,music_path=None):
    from subtitles import generate_ass, generate_srt
    from ffmpeg_utils import video_encode_args, escape_filter_value, LOUDNORM_FILTER
    # Loudnorm alone can overshoot after AAC encoding, especially for transient
    # synthetic speech. Limit at the final sample rate with makeup gain disabled.
    audio_filter=f'{LOUDNORM_FILTER},aformat=sample_rates=48000:channel_layouts=stereo,alimiter=limit=0.707945:level=false:latency=true'
    duration=end-start
    import av
    with av.open(str(source)) as container:
        has_audio=bool(container.streams.audio)
    if stage:stage('captions_audio')
    if request.silence_removal and request.audio_mode!='voiceover':
        from .audio_edit import remove_pauses
        source,transcript,start,end=remove_pauses(source,output.with_suffix('.trimmed.mp4'),transcript,start,end,has_audio,tick)
        duration=end-start
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
        if request.captions:
            import sys
            timed=output.with_suffix('.voice.json')
            run([sys.executable,'-m','factory.transcribe',str(narration),str(timed),transcript.get('language') or request.language or 'en'],tick)
            transcript=json.loads(timed.read_text(encoding='utf-8'))
            caption_start,caption_end=0,duration
    ass=output.with_suffix('.ass')
    srt=output.with_suffix('.srt')
    generate_srt(transcript,caption_start,caption_end,str(srt))
    generate_ass(transcript,caption_start,caption_end,str(ass),fontsize=18,font_name='Noto Sans',max_chars=30,effect='pop' if request.caption_style=='pop' else 'none',highlight_color='#FFFFFF' if request.caption_style=='clean' else '#FFD700')
    # Source is already a precisely extracted selected interval.
    args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-threads','2','-i',str(source)]
    width,height=(1080,1920) if request.mode=='shorts' else (request.output_height*16//9//2*2,request.output_height)
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
    if request.mode=='longs':
        graph=f'[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]'
    elif preset=='gameplay':
        if not background or not background.is_file():
            raise ValueError('Gameplay requires an authorized background asset; choose Blur or upload an asset')
        args+=['-stream_loop','-1','-threads','2','-i',str(background)]
        top=2*round(1920*request.split_ratio/2)
        bottom=1920-top
        graph=f'[0:v]scale=1080:{top}:force_original_aspect_ratio=increase,crop=1080:{top},setsar=1[top];[1:v]scale=1080:{bottom}:force_original_aspect_ratio=increase,crop=1080:{bottom},setsar=1[bottom];[top][bottom]vstack[v]'
    elif preset=='smart' and trajectory:
        graph=f"[0:v]sendcmd=f='{escape_filter_value(str(commands.resolve()))}',crop@c={crop_w}:{crop_h}:{positions[0]}:0,scale=1080:1920,setsar=1[v]"
    elif preset=='crop':
        # Explicit center framing fallback; no unverified face-tracking claim.
        graph='[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v]'
    else:
        graph='[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]'
    if request.captions and ass.exists():
        graph+=f";[v]ass=filename='{escape_filter_value(str(ass.resolve()))}'[captioned]"
        video='[captioned]'
    else:
        video='[v]'
    if request.hook:
        hookfile=output.with_suffix('.hook.txt')
        hookfile.write_text('\n'.join(textwrap.wrap(request.hook,width=26)),encoding='utf-8')
        # Windows FFmpeg builds may have no fontconfig configuration. An explicit
        # installed font avoids drawtext terminating the entire render process.
        font=''
        if os.name=='nt':
            fontpath=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf'
            if fontpath.is_file():font=f"fontfile='{escape_filter_value(str(fontpath.resolve()))}':"
        graph+=f";{video}drawtext={font}textfile='{escape_filter_value(str(hookfile.resolve()))}':expansion=none:fontcolor=white:fontsize=48:box=1:boxcolor=black@0.65:boxborderw=14:x=(w-tw)/2:y=h*0.12:enable='lt(t,3)'[hooked]"
        video='[hooked]'
    audio_map=None
    next_input=2 if preset=='gameplay' and request.mode=='shorts' else 1
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
            graph+=f';[0:a]asplit[original][side];[bed][side]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[duck];[original][duck]amix=inputs=2:normalize=0,{audio_filter}[audio]'
        else:graph+=f';[bed]{audio_filter}[audio]'
        audio_map='[audio]'
    elif has_audio and request.audio_mode!='silent':
        graph+=f';[0:a]{audio_filter}[audio]';audio_map='[audio]'
    args+=['-filter_complex_threads','1','-filter_complex',graph,'-map',video]
    args+=['-map',audio_map,'-c:a','aac','-b:a','192k','-ar','48000'] if audio_map else ['-an']
    args+=[*video_encode_args(),'-maxrate',str(request.bitrate),'-bufsize',str(request.bitrate*2),'-threads','2','-pix_fmt','yuv420p']
    if not request.preserve_fps:
        args+=['-r','30']
    args+=['-t',str(duration),'-movflags','+faststart','-progress','pipe:1',str(output)]
    if stage:stage('rendering')
    run(args,tick,duration)
    if stage:stage('validation')
    report=validate_output(output,duration,request=request,expected_audio=audio_map is not None)
    output.with_suffix('.validation.json').write_text(json.dumps({**report,'framing':framing}),encoding='utf-8')
    return output


def validate_output(path,duration,request=None,expected_audio=None):
    import av
    with av.open(str(path)) as container:
        if not container.streams.video or not container.duration or abs(container.duration/av.time_base-duration)>1:
            raise RuntimeError('Rendered video validation failed (stream/duration)')
        stream=container.streams.video[0]
        stream.thread_count=2
        if request:
            expected=(1080,1920) if request.mode=='shorts' else (request.output_height*16//9//2*2,request.output_height)
            if (stream.width,stream.height)!=expected:raise RuntimeError('Rendered resolution/aspect ratio does not match the requested output')
        if expected_audio is not None and bool(container.streams.audio)!=expected_audio:
            raise RuntimeError('Rendered audio track does not match the selected audio mode')
        frames=0;black_samples=0;sampled_frames=0
        try:
            for frame in container.decode(video=0):
                if frames % max(1,round(float(stream.average_rate or 30)))==0:
                    pixels=frame.reformat(width=64,height=64,format='gray').to_ndarray()
                    sampled_frames+=1;black_samples+=int((pixels<16).mean()>.95)
                frames+=1
        except Exception:
            raise RuntimeError('Rendered container has a corrupted video packet') from None
        if not frames:
            raise RuntimeError('Rendered video has no decodable frame')
        report={'duration':container.duration/av.time_base,'width':stream.width,'height':stream.height,'frames_decoded':frames,'audio':bool(container.streams.audio),'validated':True,'black_frame_fraction':black_samples/sampled_frames,'black_frames_sampled':sampled_frames}
    if report['audio']:
        import numpy as np
        peak=0.;samples=clipped=silent=0
        with av.open(str(path)) as container:
            try:
                for frame in container.decode(audio=0):
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
    return report


def concatenate(paths,output,tick=lambda *_:None):
    # Only application-generated file paths, never source-supplied strings.
    manifest=output.with_suffix('.concat.txt')
    manifest.write_text(''.join("file '"+p.name+"'\n" for p in paths),encoding='utf-8')
    run([ffmpeg(),'-y','-hide_banner','-loglevel','error','-f','concat','-safe','1','-i',str(manifest),'-c','copy','-movflags','+faststart',str(output)],tick)
