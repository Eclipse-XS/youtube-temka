"""Authenticated, content-verified transfer of operator-approved library assets."""
import hashlib
import os
import re
from pathlib import Path
from . import config
from .resources import preflight


class SyncedAssets(dict):
    def __init__(self):
        super().__init__()
        self.by_name = {}


def asset_path(kind, name):
    suffixes={'backgrounds':('.mp4',), 'music':('.mp3','.wav','.mp4'), 'logos':('.png',)}
    if kind not in suffixes or not re.fullmatch(r'[A-Za-z0-9_-]+\.(mp3|wav|mp4|png)', name):
        raise ValueError('Invalid library asset')
    path=config.DATA/kind/name
    if path.suffix not in suffixes[kind] or path.is_symlink() or not path.is_file():
        raise ValueError('Approved asset unavailable')
    return path


def manifest(request, timeline=None):
    """Only assets needed by this job; automatic layout uses the controller library."""
    wanted=[]
    if request.get('logo_asset'):wanted.append(('logos',request['logo_asset']))
    if request.get('background_mode')!='none' and (request.get('preset','auto') in ('auto','gameplay') or request.get('background')):
        name=request.get('background')
        if not name:
            name=next((p.name for p in sorted((config.DATA/'backgrounds').glob('*.mp4')) if not p.is_symlink()),None)
        if name:wanted.append(('backgrounds',name))
    if request.get('audio_mode')=='music' and request.get('music_asset'):
        wanted.append(('music',request['music_asset']))
    for event in (timeline or {}).get('events', []):
        library = {'image_overlay':'logos','video_overlay':'backgrounds'}.get(event['type'])
        if library:
            wanted.append((library,event['source_asset_id']))
    result=[]
    for kind,name in dict.fromkeys(wanted):
        path=asset_path(kind,name)
        with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        result.append({'kind':kind,'name':name,'size':path.stat().st_size,'sha256':digest})
    return result


def timeline_asset_files(request, background, effects, synced=None):
    synced = synced or {}
    paths = {'background':background} if request.mode == 'shorts' and background else {}
    requested = [('music',request.music_asset),('logos',request.logo_asset)]
    for effect in effects:
        if effect.kind in ('video_overlay','image_overlay'):
            requested.append(('backgrounds' if effect.kind == 'video_overlay' else 'logos',effect.asset))
    for library,name in requested:
        if name:
            paths[library+':'+name] = (getattr(synced,'by_name',{}).get((library,name)) or
                                       synced.get(library) or config.DATA/library/name)
    return paths


def timeline_asset_identities(request, background, effects, synced=None):
    from .stage_cache import file_identity

    paths = timeline_asset_files(request,background,effects,synced)
    return {key:file_identity(path) if path.is_file() else None for key,path in paths.items()}


def sync(client, items, tick=lambda:None):
    """One worker pipeline owns its cache. Keep only current-job assets, max 2 GiB."""
    root=config.DATA/'asset-cache'
    root.mkdir(parents=True,exist_ok=True)
    limit=int(os.environ.get('ASSET_CACHE_BYTES',str(2*1024**3)))
    expected={}
    for item in items:
        kind,name,digest=item['kind'],item['name'],item['sha256']
        if kind not in ('backgrounds','music','logos') or not re.fullmatch(r'[A-Za-z0-9_-]+\.(mp3|wav|mp4|png)',name) or not re.fullmatch('[a-f0-9]{64}',digest):
            raise ValueError('Invalid asset manifest')
        size=int(item['size'])
        if size<=0 or size>limit:raise ValueError('Required asset exceeds worker cache budget')
        if kind=='backgrounds' and Path(name).suffix!='.mp4':raise ValueError('Invalid background manifest')
        if kind=='logos' and Path(name).suffix!='.png':raise ValueError('Invalid logo manifest')
        expected[kind+'-'+digest+Path(name).suffix]=(item,size)
    if sum(size for _,size in expected.values())>limit:raise ValueError('Required assets exceed worker cache budget')
    for path in root.iterdir():
        if path.is_file() and path.name not in expected:path.unlink()
    paths=SyncedAssets()
    for filename,(item,size) in expected.items():
        path=root/filename
        if path.is_file():
            with path.open('rb') as source:valid=path.stat().st_size==size and hashlib.file_digest(source,'sha256').hexdigest()==item['sha256']
            if not valid:path.unlink()
        if not path.is_file():
            preflight(size)
            temporary=path.with_suffix('.part')
            try:
                digest=hashlib.sha256();count=0
                with client.stream('GET',f"/api/workers/assets/{item['kind']}/{item['name']}",params={'sha256':item['sha256']}) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as output:
                        for chunk in response.iter_bytes(256*1024):
                            count+=len(chunk)
                            if count>size:raise ValueError('Asset response exceeded verified size')
                            preflight(len(chunk));tick();digest.update(chunk);output.write(chunk)
                if count!=size or digest.hexdigest()!=item['sha256']:raise ValueError('Asset integrity verification failed')
                temporary.replace(path)
            finally:temporary.unlink(missing_ok=True)
        paths.setdefault(item['kind'],path)
        paths.by_name[(item['kind'],item['name'])]=path
    return paths
