import hashlib
import importlib.util
import io
import sqlite3
from pathlib import Path
from factory import config, deployment


def test_backup_captures_wal_and_preserves_source(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'DB',tmp_path/'jobs.sqlite3')
    with sqlite3.connect(config.DB) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE durable(value TEXT)')
        db.execute("INSERT INTO durable VALUES ('preserved')")
        db.commit()
        deployment.backup()
        with sqlite3.connect(next((tmp_path/'backups').glob('*.sqlite3'))) as saved:
            assert saved.execute('SELECT value FROM durable').fetchone()==('preserved',)
        assert db.execute('SELECT COUNT(*) FROM durable').fetchone()[0]==1


def test_corrupted_wheel_is_discarded_and_retry_verified(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('wheels',Path(__file__).parents[1]/'deploy/download-wheels.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    good=b'authentic wheel fixture'
    responses=iter([b'corrupt',good])
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(next(responses)))
    monkeypatch.setattr(module.time,'sleep',lambda *_:None)
    item={'filename':'test.whl','url':'https://example.invalid/wheel','sha256':hashlib.sha256(good).hexdigest(),'size':len(good)}
    module.download(item,tmp_path)
    assert (tmp_path/'test.whl').read_bytes()==good
    assert not list(tmp_path.glob('*.part'))
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('cache was not reused')))
    module.download(item,tmp_path)


def test_invalid_credentials_do_not_stop_readiness(tmp_path):
    missing=tmp_path/'missing.json'
    assert deployment.credential(missing,'https://example.invalid')=='AUTHORIZATION_REQUIRED'
    missing.write_text('{}')
    assert deployment.credential(missing,'https://example.invalid')=='INVALID_CREDENTIALS'
