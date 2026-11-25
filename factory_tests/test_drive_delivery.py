import hashlib
import json
from types import SimpleNamespace

import pytest

from factory import drive_delivery


def test_checkpoint_reuses_verified_media_and_rejects_changes(tmp_path):
    clip=tmp_path/'clip-1.mp4'
    clip.write_bytes(b'completed export')
    (tmp_path/'selected-1.mp4').write_bytes(b'editable source')
    digest=hashlib.sha256(clip.read_bytes()).hexdigest()
    (tmp_path/'reproducibility.json').write_text(json.dumps({'job_id':'job','outputs':[
        {'name':clip.name,'sha256':digest,'validation':{'validated':True}},
    ]}),encoding='utf-8')
    (tmp_path/'source.json').write_text('{}',encoding='utf-8')
    (tmp_path/'analysis.json').write_text('{"candidates":[]}',encoding='utf-8')
    (tmp_path/'transcript.json').write_text('{"language":"en"}',encoding='utf-8')
    job={'id':'job','result':{'outputs':[{'name':clip.name,'output_hash':digest}]}}
    request=SimpleNamespace(model_dump=lambda:{})
    outputs,raw,metadata=drive_delivery.checkpoint(tmp_path,job,request)
    assert outputs==metadata['outputs']==job['result']['outputs']
    assert raw[clip.name].name=='selected-1.mp4'
    clip.write_bytes(b'changed')
    with pytest.raises(ValueError,match='checkpoint'):
        drive_delivery.checkpoint(tmp_path,job,request)


def test_drive_preflight_closes_client_and_sanitizes_failure(monkeypatch):
    closed=[]
    def reject(*args,**kwargs):
        raise ValueError('private credential detail')
    client=SimpleNamespace(request=reject,private_destination=reject,close=lambda:closed.append(True))
    monkeypatch.setattr(drive_delivery,'Drive',lambda:client)
    with pytest.raises(ValueError,match='Reconnect Drive') as error:
        drive_delivery.preflight()
    assert 'private credential detail' not in str(error.value)
    assert closed==[True]
