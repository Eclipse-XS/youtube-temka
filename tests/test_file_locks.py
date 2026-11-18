import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import file_locks


def test_lock_preserves_contents_and_position(tmp_path):
    path=tmp_path/'state.json'
    path.write_bytes(b'{"n": 3}')
    with path.open('r+b') as file:
        file.seek(4)
        file_locks.flock(file,file_locks.LOCK_EX | file_locks.LOCK_NB)
        assert os.lseek(file.fileno(),0,os.SEEK_CUR)==4
        file_locks.flock(file,file_locks.LOCK_UN)
        assert os.lseek(file.fileno(),0,os.SEEK_CUR)==4
    assert path.read_bytes()==b'{"n": 3}'


def test_process_crash_releases_exclusive_lock(tmp_path):
    path=tmp_path/'slot.lock'
    code="""
import sys,file_locks
with open(sys.argv[1],'a+b') as file:
    file_locks.flock(file,file_locks.LOCK_EX)
    print('HELD',flush=True)
    sys.stdin.read()
"""
    child=subprocess.Popen([sys.executable,'-u','-c',code,str(path)],
                           cwd=Path(__file__).resolve().parents[1],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert child.stdout.readline().strip()=='HELD'
        with path.open('a+b') as file:
            with pytest.raises(OSError):file_locks.flock(file,file_locks.LOCK_EX | file_locks.LOCK_NB)
            child.kill();child.wait(timeout=5)
            deadline=time.monotonic()+2
            while True:
                try:
                    file_locks.flock(file,file_locks.LOCK_EX | file_locks.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.01)
            file_locks.flock(file,file_locks.LOCK_UN)
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)
        for stream in (child.stdin,child.stdout,child.stderr):stream.close()


def test_youtube_account_state_updates_on_native_platform(tmp_path,monkeypatch):
    import yt_account
    monkeypatch.setenv('YT_ACCOUNT_STATE_DIR',str(tmp_path))
    monkeypatch.setattr(yt_account,'COOLDOWN_SECONDS',60)
    monkeypatch.setattr(yt_account,'STRIKES',2)
    monkeypatch.setattr(yt_account,'STRIKE_WINDOW',180)
    assert yt_account.note_rate_limited(now=1000)==0
    assert yt_account.note_rate_limited(now=1001)==60
    assert yt_account.cooling_down(now=1002)==59
