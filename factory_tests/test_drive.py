"""Protocol tests use an HTTP fixture; these are not real Google acceptance."""
import hashlib
from pathlib import Path
import httpx
import pytest
from factory.drive import Drive, BASE, acknowledged


def client(handler):
    drive=Drive.__new__(Drive)
    drive.tokens=None
    drive.client=httpx.Client(transport=httpx.MockTransport(handler),timeout=2)
    return drive


def test_missing_range_means_zero_bytes_not_two():
    assert acknowledged(httpx.Response(308))==0
    assert acknowledged(httpx.Response(308,headers={'Range':'bytes=0-255'}))==256


def test_public_drive_folder_is_rejected_before_media_upload():
    drive=client(lambda request:httpx.Response(200,json={'id':'folder','permissions':[{'type':'anyone'}]}))
    with pytest.raises(ValueError,match='public/domain-shared'):
        drive.private_destination('folder')


def test_resumes_interrupted_upload_and_verifies_checksum(tmp_path):
    path=tmp_path/'clip.mp4'
    data=b'authorized-test-video-data'
    path.write_bytes(data)
    checkpoint=path.with_suffix('.mp4.upload-session')
    checkpoint.write_text('https://www.googleapis.com/upload/session')
    digest=hashlib.md5(data).hexdigest()
    sent=[]
    def handler(request):
        if request.method=='GET' and request.url.path==('/drive/v3/files'):
            return httpx.Response(200,json={'files':[]})
        if request.method=='PUT' and not request.content:
            return httpx.Response(308,headers={'Range':'bytes=0-7'})
        if request.method=='PUT':
            sent.append(request.content)
            assert request.headers['Content-Range']==f'bytes 8-{len(data)-1}/{len(data)}'
            return httpx.Response(200,json={'id':'verified-fixture-id'})
        return httpx.Response(200,json={'id':'verified-fixture-id','size':str(len(data)),'md5Checksum':digest})
    drive=client(handler)
    result=drive.upload(path,'folder','job-output')
    assert sent==[data[8:]]
    assert result['id']=='verified-fixture-id'
    assert not checkpoint.exists()
    assert path.exists() # Upload alone never deletes recovery files.


def test_completed_upload_is_reconciled_without_duplicate_post(tmp_path):
    path=tmp_path/'clip.mp4'
    path.write_bytes(b'video')
    digest=hashlib.md5(b'video').hexdigest()
    methods=[]
    def handler(request):
        methods.append(request.method)
        return httpx.Response(200,json={'files':[{'id':'existing','size':'5','md5Checksum':digest}]})
    drive=client(handler)
    assert drive.upload(path,'folder','job-output')['id']=='existing'
    assert methods==['GET']


def test_checksum_mismatch_preserves_local_files(tmp_path):
    path=tmp_path/'clip.mp4'
    path.write_bytes(b'video')
    def handler(request):
        return httpx.Response(200,json={'files':[{'id':'existing','size':'5','md5Checksum':'wrong'}]})
    drive=client(handler)
    with pytest.raises(ValueError,match='different content'):
        drive.upload(path,'folder','job-output')
    assert path.read_bytes()==b'video'


def test_saved_session_cannot_exfiltrate_token(tmp_path):
    path=tmp_path/'clip.mp4'
    path.write_bytes(b'video')
    path.with_suffix('.mp4.upload-session').write_text('https://attacker.invalid/session')
    drive=client(lambda request:httpx.Response(200,json={'files':[]}))
    with pytest.raises(ValueError,match='Invalid persisted'):
        drive.upload(path,'folder','job-output')


def test_original_split_oauth_is_reused_and_never_overwritten(tmp_path,monkeypatch):
    import json
    from factory.legacy_drive_oauth import SCOPE
    client_path=tmp_path/'client.json'
    token_path=tmp_path/'token.json'
    client_path.write_text(json.dumps({'installed':{'client_id':'fixture-client','client_secret':'fixture-secret'}}))
    token_path.write_text(json.dumps({'client_id':'fixture-client','scope':SCOPE,'refresh_token':'fixture-refresh'}))
    before=(client_path.read_bytes(),token_path.read_bytes())
    monkeypatch.setenv('DRIVE_OAUTH_CLIENT_FILE',str(client_path))
    monkeypatch.setenv('DRIVE_OAUTH_TOKEN_FILE',str(token_path))
    refreshes=[]
    def handler(request):
        if request.url.host=='oauth2.googleapis.com':
            refreshes.append(1)
            return httpx.Response(200,json={'access_token':'fixture-access','scope':SCOPE,'expires_in':3600})
        assert request.headers['Authorization']=='Bearer fixture-access'
        return httpx.Response(200,json={'storageQuota':{}})
    actual_client=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:actual_client(transport=httpx.MockTransport(handler),**kw))
    drive=Drive()
    try:
        drive.request('GET',BASE+'/about')
        drive.request('GET',BASE+'/about')
    finally:
        drive.close()
    assert len(refreshes)==1
    assert before==(client_path.read_bytes(),token_path.read_bytes())
