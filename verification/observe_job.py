"""Observe an already browser-created test job; no upload or job mutation."""
import json
from pathlib import Path
import sys
import time
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
prefix=sys.argv[1]
token=dotenv_values(root/'.env')['FACTORY_TOKEN']
started=time.monotonic()
last=None
with httpx.Client(base_url='http://127.0.0.1:5175',headers={'Authorization':'Bearer '+token},timeout=20,trust_env=False) as client:
    while time.monotonic()-started<1800:
        response=client.get('/api/jobs')
        response.raise_for_status()
        job=next(j for j in response.json() if j['id'].startswith(prefix))
        marker=(job['state'],job.get('error'))
        if marker!=last:
            print(json.dumps({'job':job['id'],'state':job['state'],'error':job.get('error')},ensure_ascii=True),flush=True)
            last=marker
        if job['state'] in ('READY','FAILED','BLOCKED','CANCELLED'):
            state=client.get('/api/settings').json()
            evidence={k:job[k] for k in ('id','state','worker','result','error','stages')}
            evidence['storage_after']=state['storage']
            evidence['observed_seconds']=round(time.monotonic()-started,2)
            (root/'verification'/(sys.argv[2] if len(sys.argv)>2 else 'browser-job.json')).write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
            break
        time.sleep(3)
