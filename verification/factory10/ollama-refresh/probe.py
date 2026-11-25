"""Probe two cold loads of the isolated Ollama refresh image."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

import httpx

from factory.inference import stream_generation
from factory.visual_review import VisualReview, review_payload

MODEL = 'qwen3-vl:2b-instruct'
DIGEST = 'afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e'


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', type=Path, nargs=3, help='Three authorized chronological JPEG frames')
    parser.add_argument('--container', default='factory10-ollama-refresh')
    args = parser.parse_args()
    base = 'http://127.0.0.1:11435/api'
    payload = review_payload(MODEL, [base64.b64encode(p.read_bytes()).decode() for p in args.images], 'en')
    with httpx.Client(timeout=90, trust_env=False) as client:
        tags = client.get(base+'/tags')
        tags.raise_for_status()
        if not any(m['name'] == MODEL and m['digest'] == DIGEST for m in tags.json()['models']):
            raise RuntimeError('Expected existing Instruct artifact is missing')
        if client.get(base+'/version').json()['version'] != '0.40.16':
            raise RuntimeError('Unexpected experimental server version')
        for cycle in (1, 2):
            client.post(base+'/generate', json={'model': MODEL, 'keep_alive': 0}, timeout=10).raise_for_status()
            before = docker('exec', args.container, 'nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits').strip()
            deadline = time.monotonic()+10
            while client.get(base+'/ps',timeout=2).json()['models']:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Runner did not unload')
                time.sleep(.25)
            stamp = datetime.now(timezone.utc).isoformat()
            started = time.monotonic()
            try:
                response = stream_generation(client, base+'/generate', payload, lambda _: None, started+90)
                seconds = time.monotonic()-started
                review = VisualReview.model_validate_json(response.json()['response'], context={'frame_count':3})
                if seconds > 90:
                    raise RuntimeError('Cold request exceeded 90 seconds')
                print(json.dumps({'cycle':cycle,'seconds':round(seconds,2),'gpu_free_before_mib':before,
                                  'result':review.model_dump(), 'placement':client.get(base+'/ps').json(),
                                  'container_ram':docker('stats','--no-stream','--format','{{.MemUsage}}',args.container).strip(),
                                  'gpu_used_mib':docker('exec',args.container,'nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits').strip()}), flush=True)
            finally:
                logs = docker('logs', '--since', stamp, args.container)
                print('\n'.join(line for line in logs.splitlines() if any(fragment in line for fragment in
                      ('free memory', 'watchdog timed out', 'using old values', 'gpu memory', 'using CUDA', 'offloaded', 'projector'))), flush=True)
                client.post(base+'/generate', json={'model': MODEL, 'keep_alive': 0}, timeout=10).raise_for_status()
            if ('using old values' in logs or 'watchdog timed out' in logs or
                    'using CUDA' not in logs or 'gpu memory' not in logs or 'refreshing free memory' not in logs):
                raise RuntimeError('Fresh GPU discovery and CUDA projector were not confirmed by logs')


if __name__ == '__main__':
    main()
