import json
import httpx
import pytest
from factory import youtube_oauth as oauth
from factory.legacy_drive_oauth import DriveError,OAuthClient,SCOPE


def test_youtube_consent_saves_independent_standard_token(tmp_path,monkeypatch):
    client=tmp_path/'client.json';destination=tmp_path/'youtube'/'test.json'
    client.write_text(json.dumps({'installed':{'client_id':'fixture-client','client_secret':'fixture-secret'}}))
    monkeypatch.setattr(oauth,'receive_code',lambda client,verifier:('fixture-code','http://127.0.0.1/callback'))
    requests=[]
    def exchange(self,http,fields):
        requests.append((self.scopes,fields['grant_type']))
        return {'refresh_token':'fixture-refresh'}
    monkeypatch.setattr(OAuthClient,'exchange',exchange)
    oauth.authorize(client,destination)
    saved=json.loads(destination.read_text())
    assert saved['type']=='authorized_user' and set(saved['scopes'])==set(oauth.SCOPES.split())
    assert requests==[(oauth.SCOPES,'authorization_code')]
    assert OAuthClient.read(client).scopes==SCOPE
    with pytest.raises(DriveError,match='already_exists'):oauth.authorize(client,destination)


def test_drive_only_scope_cannot_satisfy_youtube_authorization():
    client=OAuthClient('fixture','fixture',oauth.SCOPES)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'access_token':'fixture','scope':SCOPE}))) as http:
        with pytest.raises(DriveError,match='scope_mismatch'):client.exchange(http,{})
