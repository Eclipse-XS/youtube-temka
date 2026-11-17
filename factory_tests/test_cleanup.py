import os
import time
import pytest
from factory import config,store
from factory.cleanup import sweep,remove_workspace


def test_retention_never_deletes_active_jobs(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    monkeypatch.setattr(config,'DB',tmp_path/'db.sqlite3')
    running=store.create({'source':'upload:running.mp4'})
    active=store.claim('worker')
    failed=store.create({'source':'upload:failed.mp4'})
    claim=store.claim('worker2')
    store.update(failed['id'],claim['lease'],state='FAILED')
    old=time.time()-80*3600
    for job in (running,failed):
        root=config.SCRATCH/job['id']
        root.mkdir()
        path=root/'recovery.json'
        path.write_text('{}')
        os.utime(path,(old,old))
    with store.connect() as db:
        db.execute('UPDATE jobs SET seen=?',(old,))
    sweep()
    assert (config.SCRATCH/running['id']).is_dir()
    assert not (config.SCRATCH/failed['id']).exists()
    assert store.get(failed['id'])['result']['local_expired'] is True


def test_cleanup_refuses_paths_outside_scratch(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch')
    elsewhere=tmp_path/'unrelated'
    elsewhere.mkdir()
    with pytest.raises(ValueError,match='Refusing cleanup'):
        remove_workspace(elsewhere)
    assert elsewhere.exists()
