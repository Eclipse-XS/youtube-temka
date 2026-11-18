"""Conservative opt-in GPU offload after the ASR subprocess has exited."""
import os
import subprocess
import httpx
from contextlib import contextmanager


def gpu_layers(model=None):
    setting=os.environ.get('OLLAMA_GPU_LAYERS','0')
    if setting!='auto':return max(0,min(24,int(setting)))
    try:
        free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True,timeout=3).splitlines()[0])
    except (OSError,ValueError,subprocess.SubprocessError):return 0
    # Measured on the physical 4 GiB RTX 3050: this exact quantized 3B model
    # peaks near 2 GiB at 36 layers / 4096 context. Keep >=1 GiB headroom and
    # retain the older partial-offload cap for unknown or larger models.
    if model=='qwen2.5:3b' and free>=3500:return 36
    return max(0,min(24,(free-1000)//100)) if free>=1800 else 0


@contextmanager
def model_session(client,url,model):
    """Reuse one bounded model through ranking; unload before the next stage."""
    state={'layers':gpu_layers(model),'used':False}
    try:yield state
    finally:
        if state['used']:
            try:client.post(url,json={'model':model,'keep_alive':0},timeout=10)
            except httpx.HTTPError:pass  # A 60-second TTL also bounds crash retention.


def generate(client,url,payload,session=None):
    layers=gpu_layers(payload.get('model')) if session is None else session['layers']
    if session is not None:
        session['used']=True
        payload['keep_alive']=60
    payload['options']['num_gpu']=layers
    try:response=client.post(url,json=payload)
    except httpx.TimeoutException:
        if not layers:raise
        layers=0
        if session is not None:session['layers']=0
        payload['options']['num_gpu']=0
        response=client.post(url,json=payload)
    if layers and response.status_code>=500:
        if session is not None:session['layers']=0
        payload['options']['num_gpu']=0
        response=client.post(url,json=payload)
    response.raise_for_status()
    return response
