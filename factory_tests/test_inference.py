import json
import httpx
import pytest
from factory.inference import generate,gpu_layers,model_session


@pytest.mark.parametrize('failure',['timeout','server_error'])
def test_unhealthy_gpu_request_retries_once_with_cpu_offload(monkeypatch,failure):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','4')
    calls=[]
    def handler(request):
        payload=json.loads(request.content);calls.append(payload['options']['num_gpu'])
        if len(calls)==1:
            if failure=='timeout':raise httpx.ReadTimeout('GPU runner stalled',request=request)
            return httpx.Response(500)
        return httpx.Response(200,json={'response':'verified CPU response'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=generate(client,'http://fixture.invalid/api/generate',{'options':{}})
    assert calls==[4,0] and result.status_code==200


def test_cpu_timeout_does_not_retry_indefinitely(monkeypatch):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','0')
    calls=[]
    def handler(request):
        calls.append(1);raise httpx.ReadTimeout('CPU unavailable',request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):generate(client,'http://fixture.invalid',{'options':{}})
    assert len(calls)==1


def test_failed_cpu_fallback_is_not_retried_after_gpu_timeout(monkeypatch):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','4');calls=[]
    def handler(request):
        calls.append(json.loads(request.content)['options']['num_gpu'])
        if len(calls)==1:raise httpx.ReadTimeout('GPU stalled',request=request)
        return httpx.Response(500)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):generate(client,'http://fixture.invalid',{'options':{}})
    assert calls==[4,0]


@pytest.mark.parametrize('model,free,expected',[
    ('qwen2.5:3b',3962,36),('unknown:7b',3962,24),
    ('qwen2.5:3b',3000,20),('qwen2.5:3b',1700,0)])
def test_measured_3b_offload_requires_free_memory_and_preserves_unknown_model_cap(monkeypatch,model,free,expected):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','auto')
    monkeypatch.setattr('factory.inference.subprocess.check_output',lambda *a,**kw:str(free))
    assert gpu_layers(model)==expected


def test_ranking_reuses_gpu_plan_and_unloads_after_stage_failure(monkeypatch):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','auto')
    memory=iter(['3962','1500'])
    monkeypatch.setattr('factory.inference.subprocess.check_output',lambda *a,**kw:next(memory))
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'response':'fixture'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError,match='stage failed'):
            with model_session(client,'http://fixture.invalid','qwen2.5:3b') as session:
                for _ in range(2):generate(client,'http://fixture.invalid',{'model':'qwen2.5:3b','options':{}},session=session)
                raise RuntimeError('stage failed')
    assert [c['options']['num_gpu'] for c in calls[:-1]]==[36,36]
    assert all(c['keep_alive']==60 for c in calls[:-1])
    assert calls[-1]=={'model':'qwen2.5:3b','keep_alive':0}


@pytest.mark.parametrize('setting,expected_layers',[('auto',None),('4',4)])
def test_visual_request_uses_selected_placement_without_cpu_retry(monkeypatch,setting,expected_layers):
    monkeypatch.setenv('OLLAMA_GPU_LAYERS',setting)
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content)['options'])
        return httpx.Response(500)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            generate(client,'http://fixture.invalid/api/generate',{'model':'qwen3-vl:2b-instruct','images':['frame'],'options':{}})
    assert calls==[{} if expected_layers is None else {'num_gpu':expected_layers}]


@pytest.mark.parametrize('size,vram,expected',[
    (2338198648,1201898782,False),(1663513394,1663513394,False),(2338198648,1863361494,True),
])
def test_visual_preload_rejects_measured_cpu_projector_range(size,vram,expected,monkeypatch):
    import time
    from factory.inference import VisionPlacementUnavailable, prepare_visual_model
    monkeypatch.setattr('factory.inference.gpu_status',lambda: {'total_mib':4096,'free_mib':3962})
    requests=[]
    def handler(request):
        requests.append(request.method)
        if request.method=='POST':
            assert 'images' not in json.loads(request.content)
            return httpx.Response(200)
        models=[{'name':'qwen3-vl:2b-instruct','digest':'afc393e3572c',
                 'size':size,'size_vram':vram,'context_length':4096}] if len(requests)>1 else []
        return httpx.Response(200,json={'models':models})
    payload={'model':'qwen3-vl:2b-instruct','options':{'num_ctx':4096},'keep_alive':60}
    details={}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if expected:
            prepare_visual_model(client,'http://fixture.invalid/api/generate',payload,details,time.monotonic()+5)
        else:
            with pytest.raises(VisionPlacementUnavailable):
                prepare_visual_model(client,'http://fixture.invalid/api/generate',payload,details,time.monotonic()+5)
    assert requests==['GET','POST','GET']
    assert details['model_vram_bytes']==vram


def test_vision_preload_timeout_is_reported_separately(monkeypatch):
    from factory import inference
    from factory.progress import Progress
    progress=Progress(lambda *a,**k:None)
    def timeout(*args):
        raise httpx.ReadTimeout('preload stalled')
    monkeypatch.setattr(inference,'prepare_visual_model',timeout)
    payload={'model':inference.QWEN_INSTRUCT,'images':['frame'],'options':{'num_ctx':4096}}
    with httpx.Client(timeout=90) as client:
        with pytest.raises(httpx.ReadTimeout):
            inference.observed_generation(client,'http://fixture.invalid/api/generate',payload,progress,'probe',None)
    assert progress.inference_metrics[-1]['error_code']=='VISION_MODEL_PRELOAD_TIMEOUT'
    assert progress.inference_metrics[-1]['received_fragments']==0


@pytest.mark.parametrize('validated,free,expected_unload',[(True,1250,False),(True,900,True),(False,1250,True)])
def test_vision_residency_preserves_encoding_headroom(monkeypatch,validated,free,expected_unload):
    from factory import inference
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','auto')
    monkeypatch.setattr(inference,'gpu_status',lambda: {'free_mib':free})
    calls=[]
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with model_session(client,'http://fixture.invalid/api/generate',inference.QWEN_INSTRUCT) as session:
            generate(client,'http://fixture.invalid/api/generate',
                     {'model':inference.QWEN_INSTRUCT,'images':['frame'],'options':{'num_ctx':4096}},session)
            session['validated']=validated
    assert calls[0]['keep_alive']==180
    assert [item['keep_alive'] for item in calls[1:]]==([0] if expected_unload else [])


def test_cold_vision_admission_uses_measured_free_vram(monkeypatch):
    import time
    from factory import inference
    monkeypatch.setattr(inference,'gpu_status',lambda: {'total_mib':4096,'free_mib':2000})
    def handler(request):
        assert request.method=='GET'
        return httpx.Response(200,json={'models':[]})
    payload={'model':inference.QWEN_INSTRUCT,'options':{'num_ctx':4096},'keep_alive':180}
    details={}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(inference.VisionPlacementUnavailable):
            inference.prepare_visual_model(client,'http://fixture.invalid/api/generate',payload,details,time.monotonic()+5)
    assert details['free_vram_mib']==2000


def test_release_idle_vision_before_cuda_asr(monkeypatch):
    from factory import inference
    monkeypatch.setenv('OLLAMA_GPU_LAYERS','auto')
    monkeypatch.setattr(inference.config,'OLLAMA','http://fixture.invalid')
    calls=[]
    def handler(request):
        if request.method=='GET':
            return httpx.Response(200,json={'models':[
                {'model':inference.QWEN_INSTRUCT,'size':200,'size_vram':160},
                {'model':'text','size':200,'size_vram':160},
            ]})
        calls.append(json.loads(request.content))
        return httpx.Response(200)
    client=httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(inference.httpx,'Client',lambda **kwargs: client)
    inference.release_idle_vision()
    assert calls==[{'model':inference.QWEN_INSTRUCT,'keep_alive':0}]
