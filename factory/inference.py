"""Conservative opt-in GPU offload after the ASR subprocess has exited."""
import os
import subprocess


def gpu_layers():
    setting=os.environ.get('OLLAMA_GPU_LAYERS','0')
    if setting!='auto':return max(0,min(24,int(setting)))
    try:
        free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True,timeout=3).splitlines()[0])
    except (OSError,ValueError,subprocess.SubprocessError):return 0
    return max(0,min(24,(free-1000)//100)) if free>=1800 else 0


def generate(client,url,payload):
    layers=gpu_layers()
    payload['options']['num_gpu']=layers
    response=client.post(url,json=payload)
    if layers and response.status_code>=500:
        payload['options']['num_gpu']=0
        response=client.post(url,json=payload)
    response.raise_for_status()
    return response
