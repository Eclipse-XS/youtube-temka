"""Conservative opt-in GPU offload after the ASR subprocess has exited."""
import json
import os
import subprocess
import time
import httpx
from contextlib import contextmanager
from .heavy import HEAVY_LOCK
from .progress import MODEL_PROGRESS
from . import config


class ModelBudgetExceeded(httpx.RequestError):
    pass


def installed_model_digest(progress, model):
    if progress.installed_models is None:
        progress.installed_models = {}
        try:
            with httpx.Client(timeout=2,trust_env=False) as client:
                response = client.get(config.OLLAMA+'/api/tags')
                response.raise_for_status()
            progress.installed_models = {item['name']:item['digest'] for item in response.json()['models']
                                         if item.get('name') and item.get('digest')}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass
    return progress.installed_models.get(model) or progress.installed_models.get(model+':latest')


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
    with HEAVY_LOCK:
        state={'layers':gpu_layers(model),'used':False}
        try:yield state
        finally:
            if state['used']:
                try:client.post(url,json={'model':model,'keep_alive':0},timeout=10)
                except httpx.HTTPError:pass  # A 60-second TTL also bounds crash retention.


def model_placement(client,url,model):
    try:
        response=client.get(url.rsplit('/',1)[0]+'/ps',timeout=2)
        response.raise_for_status()
        for current in response.json().get('models',[]):
            if current.get('name') != model and current.get('model') != model:
                continue
            size, vram = current.get('size'), current.get('size_vram')
            device = 'unknown'
            if isinstance(size,int) and isinstance(vram,int) and size > 0 and 0 <= vram <= size:
                device = 'cpu' if vram == 0 else 'gpu' if vram == size else 'mixed'
            return {'device':device,'model_digest':current.get('digest'),'model_vram_bytes':vram,
                    'runtime_context_length':current.get('context_length')}
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        pass
    return {'device':'unknown'}


def stream_generation(client,url,payload,activity,deadline):
    read_timeout=client.timeout.read or 180
    with client.stream('POST',url,json={**payload,'stream':True},timeout=min(read_timeout,deadline-time.monotonic())) as response:
        response.raise_for_status()
        if 'application/json' in response.headers.get('content-type',''):
            response.read()
            return response
        parts=[]
        received_bytes=0
        for line in response.iter_lines():
            if time.monotonic()>=deadline:
                raise httpx.ReadTimeout('Model wall time budget reached',request=response.request)
            if not line:
                continue
            try:
                chunk=json.loads(line)
                fragment=chunk.get('response','')
                if chunk.get('error') or not isinstance(fragment,str):
                    raise ValueError('Invalid generation record')
            except (ValueError,AttributeError) as error:
                raise httpx.RemoteProtocolError('Invalid Ollama stream',request=response.request) from error
            if fragment:
                parts.append(fragment)
                received_bytes+=len(fragment.encode('utf-8'))
                if received_bytes>256*1024:
                    raise httpx.RemoteProtocolError('Ollama response exceeded its size limit',request=response.request)
                activity(len(parts))
            if chunk.get('done') is True:
                if chunk.get('done_reason') == 'length':
                    raise httpx.RemoteProtocolError('Ollama generation reached its token limit',request=response.request)
                return httpx.Response(200,json={**chunk,'response':''.join(parts)},request=response.request)
        raise httpx.RemoteProtocolError('Ollama stream ended before completion',request=response.request)


def observed_generation(client,url,payload,progress,operation,retry_reason):
    options=payload['options']
    model_type='visual' if payload.get('images') else 'text'
    context,output=options.get('num_ctx',4096),options.get('num_predict',2048)
    remaining=progress.reserve_model(model_type,context,output)
    if not remaining:
        progress.model(operation,'skipped',{'model':payload.get('model')},error_code='MODEL_BUDGET_EXHAUSTED')
        raise ModelBudgetExceeded('Job model budget exhausted')
    started=time.monotonic()
    details={'model':payload.get('model'),'model_type':model_type,'context_window':context,
             'output_token_limit':output,
             'gpu_layers_requested':options['num_gpu'],'device':'unknown',
             'received_fragments':0,'retry_reason':retry_reason,'timeout_count':0}
    progress.model(operation,'running',details)
    last_update=time.monotonic()

    def activity(fragments):
        nonlocal last_update
        details['received_fragments']=fragments
        now=time.monotonic()
        if now-last_update>=1:
            progress.model(operation,'running',details)
            last_update=now

    try:
        response=stream_generation(client,url,payload,activity,started+remaining)
        result=response.json()
        if not isinstance(result,dict):
            raise ValueError('Invalid Ollama response')
        if result.get('done_reason')=='length':
            raise ValueError('Ollama generation reached its token limit')
    except (httpx.HTTPError,ValueError) as error:
        timed_out=isinstance(error,httpx.TimeoutException)
        details['timeout_count']=int(timed_out)
        progress.model(operation,'failed',details,error_code='MODEL_TIMEOUT' if timed_out else 'MODEL_REQUEST_FAILED')
        raise
    finally:
        if progress.model_limits is not None:
            progress.model_usage['seconds']+=time.monotonic()-started

    for key in ('prompt_eval_count','eval_count','prompt_eval_duration','eval_duration','load_duration','total_duration'):
        value=result.get(key)
        if isinstance(value,int) and value>=0:
            details[key.removesuffix('_duration')+'_seconds' if key.endswith('_duration') else key]=value/1e9 if key.endswith('_duration') else value
    if details.get('eval_seconds') and 'eval_count' in details:
        details['tokens_per_second']=round(details['eval_count']/details['eval_seconds'],2)
    if details['model']:
        details.update(model_placement(client,url,details['model']))
    progress.model(operation,'completed',details)
    return response


def generate(client,url,payload,session=None):
    layers=gpu_layers(payload.get('model')) if session is None else session['layers']
    if session is not None:
        session['used']=True
        payload['keep_alive']=60
    progress=MODEL_PROGRESS.get()
    operation=progress.next_model_request() if progress else None

    def request(layer_count,retry_reason=None):
        payload['options']['num_gpu']=layer_count
        if progress:
            attempt=operation+'-cpu-fallback' if retry_reason else operation
            return observed_generation(client,url,payload,progress,attempt,retry_reason)
        response=client.post(url,json=payload)
        response.raise_for_status()
        return response

    try:
        return request(layers)
    except httpx.TimeoutException:
        if not layers:
            raise
        retry_reason='GPU request timed out'
    except httpx.HTTPStatusError as error:
        if not layers or error.response.status_code<500:
            raise
        retry_reason='GPU request returned a server error'
    if session is not None:
        session['layers']=0
    return request(0,retry_reason)
