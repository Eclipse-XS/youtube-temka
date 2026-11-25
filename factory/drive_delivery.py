"""Deliver checkpointed exports without rerunning media stages."""
import hashlib
import json
import os
import re

import httpx

from jsonfile import write_json_atomic
from .drive import BASE, Drive


def preflight():
    try:
        drive=Drive()
        try:
            parent=os.environ.get('DRIVE_PARENT_ID')
            if parent:
                drive.private_destination(parent)
            drive.request('GET', BASE+'/files', params={'pageSize':1,'fields':'files(id)'})
        finally:
            drive.close()
    except (ValueError, OSError, KeyError, TypeError, httpx.HTTPError):
        raise ValueError('Drive authorization or destination is unavailable. Reconnect Drive or select local export.') from None


def checkpoint(root, job, request):
    """Recover the exact validated media already published in the job result."""
    def load(name):
        return json.loads((root/name).read_text(encoding='utf-8'))

    try:
        outputs=job['result']['outputs']
        record=load('reproducibility.json')
        checks={item['name']:item for item in record['outputs']}
        if not outputs or record['job_id']!=job['id'] or len(checks)!=len(outputs):
            raise ValueError('Output manifest mismatch')
        raw={}
        for item in outputs:
            name=item['name']
            match=re.fullmatch(r'clip-(\d+)\.mp4',name)
            if not match and name!='long.mp4':
                raise ValueError('Unexpected output filename')
            expected=checks[name]
            if not expected['validation']['validated'] or item['output_hash']!=expected['sha256']:
                raise ValueError('Output has no matching render verification')
            with (root/name).open('rb') as file:
                if hashlib.file_digest(file,'sha256').hexdigest()!=expected['sha256']:
                    raise ValueError('Output checksum mismatch')
            original=root/(f'selected-{match[1]}.mp4' if match else 'long-source.mp4')
            if not original.is_file() or not original.stat().st_size:
                raise ValueError('Editable source is missing')
            raw[name]=original
        metadata_path=root/'metadata.json'
        metadata=load('metadata.json') if metadata_path.is_file() else {
            'job_id':job['id'],'request':request.model_dump(),'source':load('source.json'),
            'language':load('transcript.json')['language'],'candidates':load('analysis.json')['candidates'],
            'outputs':outputs,
        }
        return outputs,raw,metadata
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Drive delivery checkpoint is incomplete or changed. Existing local files were preserved.') from None


def upload(root,jid,request,outputs,raw_sources,metadata_obj,progress,update):
    artifact_paths=[root/'transcript.json',root/'metadata.json',root/'reproducibility.json',*root.glob('timeline.json'),
                    *(p for suffix in ('.srt','.vtt','.ass','.validation.json') for p in root.glob('*'+suffix)
                      if not p.name.startswith('proxy-')),
                    *(root/o['edit_transcript'] for o in outputs if o.get('edit_transcript'))]
    total_files=sum(1+bool(o.get('thumbnail'))+int(o['name'] in raw_sources) for o in outputs)+sum(p.name=='metadata.json' or (p.is_file() and p.stat().st_size>0) for p in artifact_paths)
    progress.begin('drive','UPLOADING',total_files,'files');progress.tick(0,total_files)
    drive=Drive()
    try:
        folders=drive.job_folders(jid);uploaded=[]
        for folder in folders.values():
            drive.private_destination(folder)
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
    progress.done()
