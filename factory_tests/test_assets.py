"""Controller/remote-worker asset protocol, including hostile and failed transfers."""
import hashlib
import httpx
import pytest
from factory import assets, config


@pytest.fixture
def library(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'RESERVE_BYTES',0)
    (tmp_path/'backgrounds').mkdir()
    (tmp_path/'backgrounds'/'approved.mp4').write_bytes(b'approved-background')
    return tmp_path


def test_manifest_selects_only_required_approved_assets(library):
    (library/'unrelated.txt').write_text('private')
    manifest=assets.manifest({'preset':'auto'})
    assert len(manifest)==1 and manifest[0]['name']=='approved.mp4'
    assert manifest[0]['sha256']==hashlib.sha256(b'approved-background').hexdigest()
    assert assets.manifest({'preset':'blur'})==[]
    for kind,name in [('music','../../unrelated.txt'),('secrets','approved.mp4')]:
        with pytest.raises(ValueError):assets.asset_path(kind,name)


def test_cache_is_verified_reused_repaired_and_pruned(library):
    items=assets.manifest({'preset':'auto'});calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200,content=b'approved-background')
    with httpx.Client(base_url='http://controller',transport=httpx.MockTransport(handler)) as client:
        paths=assets.sync(client,items)
        assert paths['backgrounds'].read_bytes()==b'approved-background'
        assets.sync(client,items)
        assert len(calls)==1
        paths['backgrounds'].write_bytes(b'corrupted-cache')
        assets.sync(client,items)
        assert len(calls)==2
        assets.sync(client,[])
        assert not list((library/'asset-cache').iterdir())


@pytest.mark.parametrize('content',[b'wrong',b'approved-background-extra'])
def test_incomplete_corrupt_or_oversized_download_is_not_retained(library,content):
    with httpx.Client(base_url='http://controller',transport=httpx.MockTransport(lambda _:httpx.Response(200,content=content))) as client:
        with pytest.raises(ValueError):assets.sync(client,assets.manifest({'preset':'auto'}))
    assert not list((library/'asset-cache').iterdir())


def test_cache_budget_rejects_before_network(library,monkeypatch):
    monkeypatch.setenv('ASSET_CACHE_BYTES','1')
    with httpx.Client(base_url='http://controller',transport=httpx.MockTransport(lambda _:pytest.fail('must not transfer'))) as client:
        with pytest.raises(ValueError,match='budget'):assets.sync(client,assets.manifest({'preset':'auto'}))
