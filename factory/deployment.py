"""Container-local deployment probes without credential disclosure."""
import json
import os
import sqlite3
import time
from pathlib import Path
from . import config, store
from .resources import preflight


def backup():
    if config.DB.exists():
        folder=config.DATA/'backups'
        folder.mkdir(exist_ok=True)
        with sqlite3.connect(config.DB) as source, sqlite3.connect(folder/('jobs-'+time.strftime('%Y%m%d-%H%M%S')+'.sqlite3')) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('SQLite backup validation failed; original database preserved')
        print('Consistent SQLite backup saved in /data/backups')


def whisper():
    from .heavy import HEAVY_LOCK
    with HEAVY_LOCK:return _whisper()


def _whisper():
    import numpy as np
    import ctranslate2
    from faster_whisper import WhisperModel
    device=os.environ.get('WHISPER_DEVICE','cpu')
    if device in ('auto','cuda'):
        from .inference import release_idle_vision
        release_idle_vision()
        if not ctranslate2.get_cuda_device_count():raise RuntimeError('CTranslate2 cannot initialize a CUDA device')
        device='cuda'
    else:device='cpu'
    model=WhisperModel(config.ASR_MODEL,device=device,compute_type='int8_float16' if device=='cuda' else 'int8')
    segments,_=model.transcribe(np.zeros(32000,dtype=np.float32),language='en',vad_filter=False)
    list(segments)
    print(json.dumps({'whisper':'READY','device':device,'test':'synthetic audio inference; speech accuracy unverified'}))


def readiness():
    preflight()
    remote=bool(os.environ.get('CONTROLLER_URL'))
    if not remote:
        with store.connect() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity check failed')
    for folder in (config.DATA,config.SCRATCH):
        path=folder/('.readiness-'+str(os.getpid()))
        try:path.write_text('probe')
        finally:path.unlink(missing_ok=True)
    return {'SQLite':'REMOTE_CONTROLLER' if remote else 'READY','Scratch Storage':'READY',**integrations()}


def credential(path, url, client_file=None, required_scopes=()):
    """Read-only refresh and API probe; OAuth files are never rewritten."""
    import httpx
    if not path or not Path(path).is_file():return 'AUTHORIZATION_REQUIRED'
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if client_file:
            if not Path(client_file).is_file():return 'AUTHORIZATION_REQUIRED'
            original=json.loads(Path(client_file).read_text(encoding='utf-8-sig'))['installed']
            if data.get('client_id')!=original['client_id']:return 'INVALID_CREDENTIALS'
            data={**data,'client_secret':original['client_secret']}
        scopes=data.get('scopes',data.get('scope',[]))
        if isinstance(scopes,str):scopes=scopes.split()
        if not set(required_scopes)<=set(scopes):return 'PERMISSION_DENIED'
        with httpx.Client(timeout=15,trust_env=False) as client:
            response=client.post('https://oauth2.googleapis.com/token',data={
                'client_id':data['client_id'],'client_secret':data['client_secret'],
                'refresh_token':data['refresh_token'],'grant_type':'refresh_token'})
            if response.status_code in (400,401):return 'INVALID_CREDENTIALS'
            if response.status_code==403:return 'PERMISSION_DENIED'
            if response.status_code!=200:return 'TEMPORARILY_UNAVAILABLE'
            response=client.get(url,headers={'Authorization':'Bearer '+response.json()['access_token']})
            return {200:'CONNECTED',401:'INVALID_CREDENTIALS',403:'PERMISSION_DENIED'}.get(response.status_code,'TEMPORARILY_UNAVAILABLE')
    except (KeyError,ValueError,TypeError):return 'INVALID_CREDENTIALS'
    except (OSError,httpx.HTTPError):return 'TEMPORARILY_UNAVAILABLE'


def integrations():
    statuses={}
    drive=os.environ.get('DRIVE_TOKEN_FILE','')
    legacy=os.environ.get('DRIVE_OAUTH_TOKEN_FILE','')
    if legacy and Path(legacy).is_file():
        statuses['Google Drive']=credential(legacy,'https://www.googleapis.com/drive/v3/about?fields=storageQuota',os.environ.get('DRIVE_OAUTH_CLIENT_FILE'))
    else:statuses['Google Drive']=credential(drive,'https://www.googleapis.com/drive/v3/about?fields=storageQuota')
    for label,var,default in [('YouTube','YOUTUBE_TOKEN_DIR','/run/secrets/youtube'),('Analytics','YOUTUBE_ANALYTICS_TOKEN_DIR','/run/secrets/analytics')]:
        paths=list(Path(os.environ.get(var,default)).glob('*.json'))
        url='https://www.googleapis.com/youtube/v3/channels?part=id&mine=true'
        scopes=()
        if label=='Analytics':
            from datetime import date,timedelta
            day=(date.today()-timedelta(days=3)).isoformat()
            url=f'https://youtubeanalytics.googleapis.com/v2/reports?ids=channel%3D%3DMINE&startDate={day}&endDate={day}&metrics=views'
            scopes=('https://www.googleapis.com/auth/youtube.readonly','https://www.googleapis.com/auth/yt-analytics.readonly')
        states=[credential(path,url,required_scopes=scopes) for path in paths]
        statuses[label]=('CONNECTED' if states and all(s=='CONNECTED' for s in states) else next((s for s in states if s!='CONNECTED'),'AUTHORIZATION_REQUIRED'))
    return statuses


if __name__=='__main__':
    import sys
    result={'backup':backup,'whisper':whisper,'readiness':readiness}[sys.argv[1]]()
    if result is not None:print(json.dumps(result))
