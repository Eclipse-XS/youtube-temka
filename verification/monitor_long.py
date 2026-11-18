"""Observe real multi-hour processing and sampled host/GPU/scratch use."""
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1];prefix=sys.argv[1]
token=dotenv_values(root/'.env')['FACTORY_TOKEN'];start=time.monotonic();last=None
metrics={'scratch_peak_bytes_sampled':0,'gpu_peak_used_mib_sampled':0,'sample_interval_seconds':2,'chunk_checkpoints':{}}
with httpx.Client(base_url='http://127.0.0.1:5175',headers={'Authorization':'Bearer '+token},timeout=20,trust_env=False) as client:
    while time.monotonic()-start<2400:
        job=next(j for j in client.get('/api/jobs').json() if j['id'].startswith(prefix))
        workspace=root/'scratch/controller'/job['id']
        for path in workspace.glob('transcript-*.json'):
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                metrics['chunk_checkpoints'][path.name]={'segments':len(data['segments']),'language':data['language'],'inference':data.get('inference')}
            except (OSError,ValueError):pass
        path=workspace/'transcript.json'
        if path.is_file():
            data=json.loads(path.read_text(encoding='utf-8'));metrics['global_transcript_last_end']=max((s['end'] for s in data['segments']),default=0)
        state=client.get('/api/settings').json()['storage'];metrics['scratch_peak_bytes_sampled']=max(metrics['scratch_peak_bytes_sampled'],state['scratch_bytes']);metrics['free_bytes_last']=state['free_bytes']
        try:
            used=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True,timeout=3).splitlines()[0]);metrics['gpu_peak_used_mib_sampled']=max(used,metrics['gpu_peak_used_mib_sampled'])
        except (OSError,ValueError,subprocess.SubprocessError):pass
        marker=(job['state'],job['result'].get('audio_chunks_completed'),job.get('error'))
        if marker!=last:print(json.dumps({'job':job['id'],'state':marker[0],'chunks':marker[1],'error':marker[2]}),flush=True);last=marker
        if job['state'] in ('READY','FAILED','BLOCKED','CANCELLED'):
            result={k:job[k] for k in ('id','state','worker','request','result','error','stages')};result['metrics']={**metrics,'elapsed_seconds':round(time.monotonic()-start,2)}
            (root/'verification/long-vod-job.json').write_text(json.dumps(result,indent=2),encoding='utf-8');break
        time.sleep(2)
    else:raise RuntimeError('Observation timeout; job was not cancelled')
