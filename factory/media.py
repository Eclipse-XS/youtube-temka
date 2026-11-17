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
        return 'ffmpeg'
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args, tick=lambda *_:None, duration=None, timeout=7200, env=None):
    group={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,**group)
    lines=queue.Queue()
    def read():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)
    thread=threading.Thread(target=read,daemon=True)
    thread.start()
    started=time.monotonic()
    tail=[]
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
            tail=(tail+[line])[-12:]
            if line.startswith('out_time_us='):
                try:
                    tick(float(line.split('=')[1])/1e6,duration)
                except ValueError:
                    pass
        if process.wait() != 0:
            # Do not return raw downloader logs: URLs may carry credentials.
            raise RuntimeError('Media process failed. Check codec support, source accessibility and available disk space.')
    finally:
        if process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            else:
                os.killpg(process.pid,signal.SIGKILL)
        process.wait()
        thread.join(timeout=2)


def local_source(source):
    if source.startswith('upload:'):
        name=source[7:]
        if not name or Path(name).name != name:
            raise ValueError('Invalid uploaded source identifier')
        path=config.SCRATCH/'uploads'/name
        if not path.is_file():
            raise ValueError('Uploaded source is missing')
        return path
    return None


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
            return {'title':path.stem,'platform':'local','duration':c.duration/av.time_base,'resolutions':[video.height],'size':path.stat().st_size}
    validate_url(source)
    import yt_dlp
    import ssrf_guard
    with ssrf_guard.guarded(), yt_dlp.YoutubeDL({'quiet':True,'noplaylist':True,'socket_timeout':20,'skip_download':True}) as ydl:
        item=ydl.extract_info(source,download=False)
    if item.get('is_live') or item.get('live_status') in ('is_live','is_upcoming'):
        raise ValueError('Only completed VODs are supported')
    if not item.get('duration'):
        raise ValueError('Unknown source duration; bounded processing cannot be guaranteed')
    return {'title':item.get('title'),'platform':item.get('extractor_key'),'duration':item['duration'],'resolutions':sorted({int(f['height']) for f in item.get('formats',[]) if f.get('height')}),'size':item.get('filesize'),'independent_audio':any(f.get('vcodec')=='none' and f.get('acodec') not in ('none',None) for f in item.get('formats',[]))}


def download(source,path,start,end,resolution,audio=False,tick=lambda *_:None):
    """Never fall back to downloading the full remote VOD."""
    preflight()
    local=local_source(source)
    if local:
        args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(local),'-t',str(end-start)]
        if audio:
            args+=['-vn','-ac','1','-ar','16000','-c:a','pcm_s16le']
        else:
            args+=['-c:v','libx264','-preset','fast','-c:a','aac']
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


def render(source,output,transcript,start,end,request,background=None,tick=lambda *_:None):
    from subtitles import generate_ass, generate_srt
    from ffmpeg_utils import video_encode_args, escape_filter_value, LOUDNORM_FILTER
    duration=end-start
    ass=output.with_suffix('.ass')
    srt=output.with_suffix('.srt')
    generate_srt(transcript,start,end,str(srt))
    generate_ass(transcript,start,end,str(ass),fontsize=18,font_name='Noto Sans',max_chars=30,effect='pop' if request.caption_style=='pop' else 'none',highlight_color='#FFFFFF' if request.caption_style=='clean' else '#FFD700')
    # Source is already a precisely extracted selected interval.
    args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-i',str(source)]
    width,height=(1080,1920) if request.mode=='shorts' else (request.output_height*16//9//2*2,request.output_height)
    if request.mode=='longs':
        graph=f'[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]'
    elif request.preset=='gameplay':
        if not background or not background.is_file():
            raise ValueError('Gameplay requires an authorized background asset; choose Blur or upload an asset')
        args+=['-stream_loop','-1','-i',str(background)]
        top=2*round(1920*request.split_ratio/2)
        bottom=1920-top
        graph=f'[0:v]scale=1080:{top}:force_original_aspect_ratio=increase,crop=1080:{top},setsar=1[top];[1:v]scale=1080:{bottom}:force_original_aspect_ratio=increase,crop=1080:{bottom},setsar=1[bottom];[top][bottom]vstack[v]'
    elif request.preset=='crop':
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
        graph+=f";{video}drawtext=textfile='{escape_filter_value(str(hookfile.resolve()))}':expansion=none:fontcolor=white:fontsize=48:box=1:boxcolor=black@0.65:boxborderw=14:x=(w-tw)/2:y=h*0.12:enable='lt(t,3)'[hooked]"
        video='[hooked]'
    args+=['-filter_complex_threads','1','-filter_complex',graph,'-map',video,'-map','0:a:0?',*video_encode_args(),'-maxrate',str(request.bitrate),'-bufsize',str(request.bitrate*2),'-threads','2','-pix_fmt','yuv420p']
    if not request.preserve_fps:
        args+=['-r','30']
    args+=['-c:a','aac','-af',LOUDNORM_FILTER,'-t',str(duration),'-movflags','+faststart','-progress','pipe:1',str(output)]
    run(args,tick,duration)
    validate_output(output,duration)
    return output


def validate_output(path,duration):
    import av
    with av.open(str(path)) as container:
        if not container.streams.video or not container.duration or abs(container.duration/av.time_base-duration)>1:
            raise RuntimeError('Rendered video validation failed (stream/duration)')
        if next(container.decode(video=0),None) is None:
            raise RuntimeError('Rendered video has no decodable frame')


def concatenate(paths,output,tick=lambda *_:None):
    # Only application-generated file paths, never source-supplied strings.
    manifest=output.with_suffix('.concat.txt')
    manifest.write_text(''.join("file '"+p.name+"'\n" for p in paths),encoding='utf-8')
    run([ffmpeg(),'-y','-hide_banner','-loglevel','error','-f','concat','-safe','1','-i',str(manifest),'-c','copy','-movflags','+faststart',str(output)],tick)
