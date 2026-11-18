import os
import socket
import threading
import time
from . import store
from .resources import usage,hardware


def local_loop(stop):
    from .pipeline import process
    worker=os.environ.get('WORKER_ID','controller-'+socket.gethostname())
    from .cleanup import sweep
    from .inference import HEAVY_LOCK
    last_sweep=0
    while not stop.is_set():
        if time.monotonic()-last_sweep>60:
            sweep()
            last_sweep=time.monotonic()
        store.heartbeat(worker,hardware())
        if not HEAVY_LOCK.acquire(False):
            stop.wait(1);continue
        try:
            claimed=store.claim(worker)
            if claimed:
                try:process(claimed)
                except Exception:
                    try:store.update(claimed['job']['id'],claimed['lease'],state='FAILED',error='Unexpected worker failure; checkpoints preserved. Retry after checking configuration.')
                    except InterruptedError:pass
            else:stop.wait(3)
        finally:HEAVY_LOCK.release()


class RemoteStore:
    def __init__(self,client):
        self.client=client

    def update(self,jid,lease,**kwargs):
        response=self.client.post('/api/workers/jobs/'+jid,json={'lease':lease,**kwargs})
        if response.status_code==409:
            raise InterruptedError('Worker lease lost')
        response.raise_for_status()

    def get(self,jid):
        response=self.client.get('/api/jobs/'+jid)
        response.raise_for_status()
        return response.json()

    def list_jobs(self):
        response=self.client.get('/api/jobs')
        response.raise_for_status()
        return response.json()


def main():
    import httpx
    from . import pipeline
    from .config import TOKEN
    url=os.environ.get('CONTROLLER_URL','')
    if not url or len(TOKEN)<32:
        raise SystemExit('Set CONTROLLER_URL and the controller FACTORY_TOKEN (32+ characters). Use a private LAN/Tailscale endpoint.')
    worker=os.environ.get('WORKER_ID',socket.gethostname())
    with httpx.Client(base_url=url,headers={'Authorization':'Bearer '+TOKEN},timeout=30,trust_env=False) as client:
        pipeline.store=RemoteStore(client)
        while True:
            try:
                response=client.post('/api/workers/claim',json={'worker':worker,'resources':hardware()})
                response.raise_for_status()
                claim=response.json()
                if claim:
                    from .assets import sync
                    try:
                        assets=sync(client,claim.get('assets',[]),lambda:pipeline.store.update(claim['job']['id'],claim['lease']))
                        pipeline.process(claim,assets=assets)
                    except InterruptedError:pass
                    except (httpx.HTTPError,ValueError,OSError,RuntimeError):
                        try:pipeline.store.update(claim['job']['id'],claim['lease'],state='BLOCKED',error='Worker asset synchronization failed; check the approved library, connection and cache budget, then retry.')
                        except InterruptedError:pass
                else:
                    time.sleep(3)
            except (httpx.HTTPError,ValueError):
                time.sleep(10)


if __name__=='__main__':
    main()
