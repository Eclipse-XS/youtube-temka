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
    last_sweep=0
    while not stop.is_set():
        if time.monotonic()-last_sweep>60:
            sweep()
            last_sweep=time.monotonic()
        store.heartbeat(worker,hardware())
        claimed=store.claim(worker)
        if claimed:
            process(claimed)
        else:
            stop.wait(3)


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
                    pipeline.process(claim)
                else:
                    time.sleep(3)
            except httpx.HTTPError:
                time.sleep(10)


if __name__=='__main__':
    main()
