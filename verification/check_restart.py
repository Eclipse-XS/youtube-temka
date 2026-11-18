"""Stop only this test controller during a browser-created disposable render.

This deliberately interrupts processing, preserves checkpoints and waits for the
normal lease expiry. The operator's manual Retry remains a browser action.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
token=dotenv_values(root/'.env')['FACTORY_TOKEN'];prefix=sys.argv[1]
evidence={};started=time.monotonic()
with httpx.Client(base_url='http://127.0.0.1:5175',headers={'Authorization':'Bearer '+token},timeout=10,trust_env=False) as client:
    while time.monotonic()-started<180:
        jobs=client.get('/api/jobs').json();job=next(j for j in jobs if j['id'].startswith(prefix))
        if job['result'].get('active_stage')=='rendering':
            evidence['before']={'id':job['id'],'state':job['state'],'stages':job['stages']}
            evidence['checkpoints_before']=[p.name for p in (root/'scratch/controller'/job['id']).iterdir()]
            subprocess.run(['docker','compose','--profile','controller','restart','-t','1','controller'],check=True,stdout=subprocess.DEVNULL)
            print('Controller restarted during actual rendering',flush=True)
            break
        if job['state'] in ('FAILED','BLOCKED','READY'):raise RuntimeError('Job finished before the requested interruption')
        time.sleep(.5)
    else:raise RuntimeError('Render stage did not start in time')
    while time.monotonic()-started<420:
        try:
            job=client.get('/api/jobs/'+job['id']).json()
            if job['state']=='BLOCKED':
                evidence['after']={'state':job['state'],'error':job['error'],'stages':job['stages']}
                evidence['checkpoints_retained']=[p.name for p in (root/'scratch/controller'/job['id']).iterdir()]
                evidence['elapsed_seconds']=round(time.monotonic()-started,2)
                (root/'verification/restart-result.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
                print('Lease expired into BLOCKED; checkpoints retained; browser retry can proceed',flush=True)
                break
        except (httpx.HTTPError,ValueError,KeyError):pass
        time.sleep(2)
    else:raise RuntimeError('Restart recovery did not reach BLOCKED')
