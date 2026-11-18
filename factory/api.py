import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import threading
import time
import uuid
import re
import mimetypes
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from . import config, store, media
from .models import JobRequest
from .resources import preflight, usage


@asynccontextmanager
async def lifespan(app):
    config.initialize()
    from .worker import local_loop
    stop=threading.Event()
    if os.environ.get('FACTORY_LOCAL_WORKER','1')=='1':
        thread=threading.Thread(target=local_loop,args=(stop,),daemon=True)
        thread.start()
        app.state.local_worker=thread
    if os.environ.get('FACTORY_PUBLISHER','1')=='1':
        from .publisher import loop
        threading.Thread(target=loop,args=(stop,),daemon=True).start()
    if os.environ.get('FACTORY_ANALYTICS','1')=='1':
        from .analytics import loop as analytics_loop
        threading.Thread(target=analytics_loop,args=(stop,),daemon=True).start()
    yield
    stop.set()


app=FastAPI(title='AI Content Factory',lifespan=lifespan)


def drive_is_configured():
    standard=os.environ.get('DRIVE_TOKEN_FILE','')
    legacy=[os.environ.get('DRIVE_OAUTH_CLIENT_FILE',''),os.environ.get('DRIVE_OAUTH_TOKEN_FILE','')]
    return bool((standard and Path(standard).is_file()) or all(p and Path(p).is_file() for p in legacy))


@app.middleware('http')
async def authenticate(request, call_next):
    from fastapi.responses import JSONResponse
    if request.url.path not in ('/health','/api/session'):
        provided=request.headers.get('Authorization','').removeprefix('Bearer ') or request.cookies.get('factory_session','')
        if len(config.TOKEN)<32:
            return JSONResponse({'detail':'Set FACTORY_TOKEN to a random secret of at least 32 characters before using this controller'},status_code=503)
        if not hmac.compare_digest(provided,config.TOKEN):
            return JSONResponse({'detail':'Controller authentication required'},status_code=401)
    return await call_next(request)


@app.get('/health')
def health():
    worker=getattr(app.state,'local_worker',None)
    if worker is not None and not worker.is_alive():raise HTTPException(503,'Local processing worker stopped; inspect controller logs')
    return {'status':'ok','configured':len(config.TOKEN)>=32,'worker_alive':worker is None or worker.is_alive()}


class Login(BaseModel):
    token: str = Field(max_length=256)


@app.post('/api/session')
def login(body:Login):
    from fastapi.responses import JSONResponse
    if len(config.TOKEN)<32 or not hmac.compare_digest(body.token,config.TOKEN):
        raise HTTPException(401,'Invalid controller token or controller not configured')
    response=JSONResponse({'authenticated':True})
    response.set_cookie('factory_session',body.token,httponly=True,samesite='strict',secure=os.environ.get('FACTORY_HTTPS')=='1')
    return response


@app.delete('/api/session')
def logout():
    from fastapi.responses import JSONResponse
    response=JSONResponse({'authenticated':False})
    response.delete_cookie('factory_session')
    return response


@app.get('/api/settings')
def settings():
    from .model_setup import status
    from .publisher import channels
    from .tts import status as tts_status
    return {'storage':usage(),'workers':store.workers(),'channels':channels(),'drive_configured':drive_is_configured(),'inference_mode':os.environ.get('OLLAMA_GPU_LAYERS','0'),'ollama_model':config.MODEL,'whisper_model':config.ASR_MODEL,'model_setup':status(),'tts':tts_status(),'publishing':{'enabled':bool(list(Path(os.environ.get('YOUTUBE_TOKEN_DIR','secrets/youtube')).glob('*.json'))),'state':'CONNECTED' if channels() else 'YOUTUBE_AUTH_REQUIRED','reason':'Use the one-time Desktop OAuth consent, discover the channel, then approve a versioned publishing draft. Public publishing requires explicit channel authorization.'},'limits':{'interval_minutes':1440,'audio_chunk_minutes':15,'concurrent_jobs':1},'notes':['Smart Crop samples faces on CPU; no-face footage falls back to a blurred background.','GPU inference is sequential; CPU/int8 is the default.','Remote workers process URL jobs with Drive enabled; uploaded local sources stay on controller.','Failed/cancelled scratch workspaces expire after 72 hours; running jobs are excluded.']}


@app.post('/api/settings/check-ollama')
def check_ollama():
    import httpx
    try:
        response=httpx.get(config.OLLAMA+'/api/tags',timeout=5,trust_env=False)
        response.raise_for_status()
        found=config.MODEL in [m['name'] for m in response.json()['models']]
        return {'available':found,'action':None if found else 'ollama pull '+config.MODEL}
    except (httpx.HTTPError,KeyError,ValueError):
        return {'available':False,'action':'Start Ollama, then run: ollama pull '+config.MODEL}


@app.post('/api/tts/setup')
def tts_setup():
    from .tts import setup,status
    if not status()['runtime']:raise HTTPException(409,'Rebuild with WITH_TTS=1 for optional narration. Original audio works without it.')
    return setup()


class VoicePreview(BaseModel):
    voice:str=Field(pattern=r'^(af_heart|af_bella|am_michael|ef_dora|em_alex)$')


@app.post('/api/tts/preview')
def voice_preview(body:VoicePreview):
    from .tts import synthesize,VOICES
    language=VOICES[body.voice]
    text='A clear, friendly voice for your next video.' if language=='en' else 'Una voz clara y agradable para tu próximo vídeo.'
    folder=config.DATA/'voice-previews';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(body.voice+'.wav')
    try:
        if not path.is_file():synthesize(text,body.voice,1,language,path)
    except (ValueError,RuntimeError) as error:raise HTTPException(409,str(error)) from None
    return {'url':'/api/tts/previews/'+body.voice+'.wav'}


@app.get('/api/tts/previews/{name}')
def voice_file(name:str):
    from .tts import VOICES
    if name not in [v+'.wav' for v in VOICES]:raise HTTPException(404,'Unknown voice')
    path=config.DATA/'voice-previews'/name
    if not path.is_file():raise HTTPException(404,'Generate the preview first')
    return FileResponse(path,media_type='audio/wav')


@app.post('/api/settings/setup-model')
def setup_model():
    from .model_setup import start
    return start()


class Models(BaseModel):
    ollama_model:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$')
    whisper_model:str=Field(pattern=r'^(tiny|base|small|medium|large-v3|large-v3-turbo)$')


@app.post('/api/settings/models')
def configure_models(body:Models):
    from .model_setup import _lock
    from jsonfile import write_json_atomic
    if _lock.locked():
        raise HTTPException(409,'Wait for the active model setup to finish')
    config.initialize()
    write_json_atomic(config.DATA/'settings.json',body.model_dump())
    config.MODEL=body.ollama_model
    config.ASR_MODEL=body.whisper_model
    return {'saved':True,'action':'Check availability or download the configured model. Existing jobs retain their model selection.'}


@app.post('/api/settings/check-drive')
def check_drive():
    from .drive import Drive, BASE
    try:
        drive=Drive()
        try:
            drive.request('GET',BASE+'/about',params={'fields':'storageQuota'})
        finally:
            drive.close()
        return {'authorized':True}
    except (ValueError,KeyError,OSError):
        raise HTTPException(409,'Drive authorization unavailable. Configure the existing authorized-user JSON with Drive scope; original credential files are not modified.') from None


class Source(BaseModel):
    source:str=Field(max_length=2048)


@app.post('/api/probe')
def probe(body:Source):
    try:
        return media.probe(body.source)
    except Exception:
        raise HTTPException(400,'Source cannot be probed. Use a completed public YouTube/Twitch VOD or a valid uploaded video; verify network access.') from None


@app.post('/api/uploads')
async def upload(file:UploadFile=File(...), rights_confirmed:bool=Form(...), background:bool=Form(False),music:bool=Form(False)):
    if not rights_confirmed:
        raise HTTPException(422,'Source/background rights confirmation is required')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in (('.mp3','.wav','.mp4') if music else ('.mp4','.mkv','.mov')) or (background and suffix!='.mp4'):
        raise HTTPException(422,'Upload MP4/MKV/MOV; backgrounds must be MP4')
    folder=config.DATA/'music' if music else ((config.DATA/'backgrounds') if background else config.SCRATCH/'uploads')
    folder.mkdir(parents=True,exist_ok=True)
    name=uuid.uuid4().hex+suffix
    target=folder/name
    try:
        with target.open('xb') as output:
            while chunk:=await file.read(1024*1024):
                preflight(len(chunk))
                if target.stat().st_size+len(chunk)>2*1024**3:
                    raise ValueError('Upload exceeds 2 GB; use a bounded source URL or a smaller file')
                output.write(chunk)
        if not background and not music:
            metadata=media.probe('upload:'+name)
        else:
            metadata=None
    except Exception:
        target.unlink(missing_ok=True)
        raise HTTPException(400,'Upload failed validation or exceeded available storage') from None
    finally:
        await file.close()
    return {'source':'upload:'+name,'name':name,'metadata':metadata}


@app.get('/api/backgrounds')
def backgrounds():
    return [p.name for p in (config.DATA/'backgrounds').glob('*.mp4')]


@app.get('/api/assets/music')
def music_assets():
    return [p.name for p in (config.DATA/'music').glob('*') if p.suffix in ('.mp3','.wav','.mp4')]


@app.post('/api/jobs',status_code=201)
def create(body:JobRequest):
    body.asr_model=body.asr_model or config.ASR_MODEL
    body.llm_model=body.llm_model or config.MODEL
    if body.publish_channel:body.metadata_preferences=store.preferences(body.publish_channel)
    if body.publish_automatic:
        from .publisher import channels
        policy=next((c for c in channels() if c['id']==body.publish_channel),None)
        if not policy or not policy['public_allowed'] or not policy['automatic']:
            raise HTTPException(409,'Explicitly enable automatic public publishing for this authenticated channel first')
    try:
        if body.source.startswith('edit:'):
            _,origin,index=body.source.split(':')
            original=store.get(origin)
            if not original or original['state']!='READY' or not original['result']['outputs'][int(index)].get('edit_source'):raise ValueError('Editable source unavailable; re-upload this older source once')
        elif not media.local_source(body.source):
            media.validate_url(body.source)
    except (ValueError,IndexError,KeyError) as error:
        raise HTTPException(422,str(error)) from None
    try:
        preflight()
    except RuntimeError as error:
        raise HTTPException(409,str(error)) from None
    return store.create(body.model_dump())


@app.get('/api/jobs')
def jobs():
    return store.list_jobs()


@app.get('/api/jobs/{jid}')
def get_job(jid:str):
    value=store.get(jid)
    if not value:
        raise HTTPException(404,'Job not found')
    return value


@app.get('/api/jobs/{jid}/events')
def events(jid:str):
    get_job(jid)
    return store.events(jid)


@app.post('/api/jobs/{jid}/cancel')
def cancel(jid:str):
    store.cancel(jid)
    return get_job(jid)


@app.post('/api/jobs/{jid}/retry')
def retry(jid:str):
    if not store.retry(jid):
        raise HTTPException(409,'Only failed, blocked or cancelled jobs can be retried')
    return get_job(jid)


class Approval(BaseModel):
    approved:bool


@app.post('/api/jobs/{jid}/outputs/{index}/approve')
def approve(jid:str,index:int,body:Approval):
    try:
        if index<0:
            raise ValueError('Invalid output')
        store.approve(jid,index,body.approved)
    except (ValueError,IndexError):
        raise HTTPException(409,'Output unavailable or not complete') from None
    return get_job(jid)


@app.post('/api/jobs/{jid}/metadata')
def generate_metadata(jid:str):
    from .drafts import regenerate
    from .inference import HEAVY_LOCK
    if not HEAVY_LOCK.acquire(False):raise HTTPException(409,'The processing slot is busy. Metadata regeneration can run after the current GPU task finishes.')
    try:return regenerate(jid)
    except (ValueError,KeyError,IndexError) as error:raise HTTPException(409,str(error)) from None
    finally:HEAVY_LOCK.release()


class MetadataEdit(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=100)
    alternative_titles:list[str]|None=None
    description:str|None=Field(default=None,min_length=1,max_length=5000)
    tags:list[str]|None=None
    hashtags:list[str]|None=None
    category_id:str|None=None
    metadata_language:str|None=None
    thumbnail_text:str|None=Field(default=None,max_length=60)


@app.patch('/api/jobs/{jid}/outputs/{index}/metadata')
def edit_metadata(jid:str,index:int,body:MetadataEdit):
    from .drafts import revise
    try:return revise(jid,index,body.model_dump(exclude_none=True))
    except (ValueError,KeyError,IndexError) as error:raise HTTPException(409,str(error)) from None


@app.get('/api/jobs/{jid}/outputs/{index}/metadata/history')
def metadata_history(jid:str,index:int):
    get_job(jid)
    return store.metadata_history(jid,index)


@app.get('/api/jobs/{jid}/files/{name}')
def output(jid:str,name:str,request:Request):
    job=get_job(jid)
    manifests={o['name']:o.get('drive') for o in job['result'].get('outputs',[])}
    for item in job['result'].get('outputs',[]):
        if item.get('thumbnail'):
            manifests[item['thumbnail']['name']]=item['thumbnail'].get('drive')
    manifests.update(job['result'].get('artifacts',{}))
    allowed=set(manifests)|{'transcript.json','transcript.srt','transcript.vtt'}
    if name not in allowed:
        raise HTTPException(404,'Artifact not found')
    root=config.SCRATCH/jid
    path=root/name
    if path.is_file():
        return FileResponse(path)
    remote=manifests.get(name)
    if not remote:
        raise HTTPException(410,'Local artifact expired or is not available; inspect the job and Drive link')
    from .drive import Drive,BASE,CHUNK
    size=int(remote['size'])
    first,last=0,size-1
    ranged=request.headers.get('Range')
    if ranged:
        match=re.fullmatch(r'bytes=(\d+)-(\d*)',ranged)
        if not match:
            raise HTTPException(416,'Use a single forward byte range')
        first=int(match.group(1))
        last=min(int(match.group(2)) if match.group(2) else size-1,first+CHUNK-1,size-1)
        if first>last:
            raise HTTPException(416,'Range outside artifact')
    drive=Drive()
    context=drive.client.stream('GET',BASE+'/files/'+remote['id'],params={'alt':'media','supportsAllDrives':'true'},headers={'Range':f'bytes={first}-{last}'})
    response=context.__enter__()
    if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {first}-{last}/{size}':
        context.__exit__(None,None,None)
        drive.close()
        raise HTTPException(502,'Drive did not honor the requested artifact range')
    def chunks():
        try:
            remaining=last-first+1
            for chunk in response.iter_bytes(256*1024):
                if len(chunk)>remaining:
                    raise ValueError('Drive artifact exceeded verified size')
                remaining-=len(chunk)
                yield chunk
        finally:
            context.__exit__(None,None,None)
            drive.close()
    headers={'Accept-Ranges':'bytes','Content-Length':str(last-first+1)}
    if ranged:
        headers['Content-Range']=f'bytes {first}-{last}/{size}'
    return StreamingResponse(chunks(),status_code=206 if ranged else 200,headers=headers,media_type=mimetypes.guess_type(name)[0] or 'application/octet-stream')


class Worker(BaseModel):
    worker:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    resources:dict=Field(default_factory=dict)


@app.post('/api/workers/heartbeat')
def heartbeat(body:Worker):
    store.heartbeat(body.worker,body.resources)
    return {'ok':True}


@app.post('/api/workers/claim')
def claim(body:Worker):
    store.heartbeat(body.worker,body.resources)
    claimed=store.claim(body.worker,remote=True)
    if claimed:
        from .assets import manifest
        try:
            result=claimed['job']['result']
            if 'asset_manifest' not in result:
                result['asset_manifest']=manifest(claimed['job']['request'])
                store.update(claimed['job']['id'],claimed['lease'],result={'asset_manifest':result['asset_manifest']})
            claimed['assets']=result['asset_manifest']
        except ValueError as error:
            store.update(claimed['job']['id'],claimed['lease'],state='BLOCKED',error=str(error))
            return None
    return claimed


@app.get('/api/workers/assets/{kind}/{name}')
def worker_asset(kind:str,name:str,sha256:str):
    import hashlib
    from .assets import asset_path
    try:path=asset_path(kind,name)
    except ValueError:raise HTTPException(404,'Approved asset unavailable') from None
    with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    if not hmac.compare_digest(digest,sha256):
        raise HTTPException(409,'Asset changed; retry to fetch the current approved version')
    return FileResponse(path)


class Checkpoint(BaseModel):
    lease:str=Field(max_length=64)
    state:str|None=None
    result:dict|None=None
    error:str|None=Field(default=None,max_length=500)
    current:float|None=None
    total:float|None=None
    stage_update:dict|None=None


@app.post('/api/workers/jobs/{jid}')
def checkpoint(jid:str,body:Checkpoint):
    states={'PROBING','DOWNLOADING','TRANSCRIBING','ANALYZING','RENDERING','UPLOADING','READY','FAILED','BLOCKED'}
    if body.state and body.state not in states:
        raise HTTPException(422,'Invalid worker state')
    try:
        store.update(jid,**body.model_dump())
    except InterruptedError:
        raise HTTPException(409,'Worker lease lost or job cancelled') from None
    return {'ok':True}


@app.get('/api/publisher')
def publisher():
    from .publisher import channels, history
    return {'channels':channels(),'publications':history()}


@app.post('/api/publisher/discover')
def discover_channels():
    from .publisher import discover_channels
    return discover_channels()


@app.get('/api/analytics')
def analytics_dashboard():
    from .analytics import snapshot
    return snapshot()


@app.post('/api/analytics/discover')
def discover_analytics():
    from .analytics import discover
    return discover()


@app.post('/api/analytics/{channel}/sync')
def sync_analytics(channel:str):
    from .analytics import start_sync
    try:return start_sync(channel)
    except ValueError as error:raise HTTPException(409,str(error)) from None


class ChannelPreferences(BaseModel):
    metadata_language:str|None=Field(default=None,pattern=r'^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$')
    category_id:str|None=Field(default=None,pattern=r'^\d{1,3}$')
    description_footer:str=Field(default='',max_length=500)
    review_first:bool=True
    auto_approve:bool=False
    max_silence_fraction:float=Field(default=.65,ge=.1,le=.8)
    timezone:str=Field(default='Europe/Kyiv',max_length=80)


class Policy(BaseModel):
    daily_limit:int=Field(default=3,ge=1,le=20)
    public_allowed:bool=False
    automatic:bool=False
    interval_minutes:int=Field(default=120,ge=30,le=1440)
    preferences:ChannelPreferences|None=None


@app.post('/api/publisher/channels/{channel}/policy')
def policy(channel:str,body:Policy):
    from .publisher import set_policy
    try:
        if body.preferences:
            from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
            try:ZoneInfo(body.preferences.timezone)
            except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid IANA timezone, for example Europe/Kyiv') from None
            from .metadata import CATEGORIES
            if body.preferences.category_id and body.preferences.category_id not in CATEGORIES:raise ValueError('Choose a supported YouTube category')
        set_policy(channel,**body.model_dump())
        return {'ok':True}
    except ValueError as error:
        raise HTTPException(409,str(error)) from None


class Publication(BaseModel):
    job:str=Field(pattern=r'^[a-f0-9]{32}$')
    output:int=Field(ge=0)
    channel:str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    title:str|None=Field(default=None,min_length=1,max_length=100)
    description:str|None=Field(default=None,max_length=5000)
    privacy:str='private'
    publish_at:str|None=None


@app.post('/api/publisher/queue')
def queue_publication(body:Publication):
    from .publisher import enqueue
    values=body.model_dump()
    values['jid']=values.pop('job')
    values['index']=values.pop('output')
    try:
        return {'id':enqueue(**values)}
    except ValueError as error:
        raise HTTPException(409,str(error)) from None


@app.post('/api/publisher/{pid}/retry')
def retry_publication(pid:str):
    from .publisher import retry
    if not retry(pid):
        raise HTTPException(409,'Only failed uploads can resume. An UNCERTAIN outcome requires YouTube Studio reconciliation.')
    return {'ok':True}


@app.post('/api/publisher/{pid}/reconcile')
def reconcile_publication(pid:str):
    from .publisher import reconcile
    try:
        reconcile(pid)
    except ValueError as error:
        raise HTTPException(409,str(error)) from None
    return {'ok':True}


class PublicationEdit(BaseModel):
    title:str=Field(min_length=1,max_length=100)
    description:str=Field(default='',max_length=5000)
    privacy:str='private'
    publish_at:str|None=None


@app.patch('/api/publisher/{pid}')
def edit_publication(pid:str,body:PublicationEdit):
    from .publisher import edit
    try:edit(pid,**body.model_dump())
    except ValueError as error:raise HTTPException(409,str(error)) from None
    return {'ok':True}
