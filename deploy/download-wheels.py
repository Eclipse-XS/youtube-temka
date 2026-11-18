"""Download immutable GPU wheels, validate SHA256, discard invalid partials.

Usage: python deploy/download-wheels.py [cache-directory]
The same cache may be prefilled offline. Never accepts an unverified wheel.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import urllib.request


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def download(item, folder):
    target=folder/item['filename']
    if target.exists() and digest(target)==item['sha256']:
        print('Verified cached '+target.name,flush=True)
        return
    target.unlink(missing_ok=True)
    partial=target.with_suffix('.part')
    seed=Path('/seed')/item['filename']
    candidates=[seed]+list((Path.home()/'.cache/pip').rglob('*.body'))
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size==item['size'] and digest(candidate)==item['sha256']:
            shutil.copyfile(candidate,target)
            print('Reused verified local wheel '+target.name,flush=True)
            return
    for attempt in range(1,6):
        partial.unlink(missing_ok=True)
        try:
            print(f"Downloading {target.name}, attempt {attempt}/5",flush=True)
            started=time.monotonic()
            with urllib.request.urlopen(item['url'],timeout=60) as response, partial.open('wb') as dest:
                while chunk:=response.read(1024*1024):
                    dest.write(chunk)
                    if time.monotonic()-started>1800:raise TimeoutError('Download exceeded 30 minutes')
            if partial.stat().st_size!=item['size'] or digest(partial)!=item['sha256']:
                raise ValueError('Wheel size/SHA256 mismatch; corrupted partial discarded')
            partial.replace(target)
            return
        except (OSError,ValueError) as error:
            partial.unlink(missing_ok=True)
            if attempt==5:raise RuntimeError('Verified wheel download failed: '+target.name) from error
            print(type(error).__name__+'; retrying verified download',flush=True)
            time.sleep(min(attempt*2,10))


if __name__=='__main__':
    folder=Path(sys.argv[1] if len(sys.argv)>1 else 'deploy/wheels')
    folder.mkdir(parents=True,exist_ok=True)
    for item in json.loads(Path(__file__).with_name('gpu-wheels.json').read_text()):download(item,folder)
