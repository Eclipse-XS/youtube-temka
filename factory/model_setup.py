"""One explicit, observable initial Ollama model download from Settings."""
import json
import threading
import time
import httpx
from jsonfile import write_json_atomic
from . import config

_lock=threading.Lock()


def status():
    path=config.DATA/'model-setup.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return None


def start():
    if not _lock.acquire(blocking=False):
        return {'started':False,'reason':'A model download is already running'}
    config.initialize()
    def record(**data):
        write_json_atomic(config.DATA/'model-setup.json',{'model':config.MODEL,**data})
    def pull():
        started=time.monotonic()
        try:
            record(state='CONNECTING')
            with httpx.Client(timeout=600,trust_env=False) as client:
                with client.stream('POST',config.OLLAMA+'/api/pull',json={'model':config.MODEL,'stream':True}) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic()-started>1800:
                            raise TimeoutError('Model setup timed out')
                        item=json.loads(line)
                        if item.get('error'):
                            raise ValueError('Ollama rejected the configured model')
                        record(state='READY' if item.get('status')=='success' else 'DOWNLOADING',status=item.get('status'),current=item.get('completed'),total=item.get('total'))
        except Exception:
            record(state='FAILED',error='Start the Ollama service and check available disk space/model name, then retry setup.')
        finally:
            _lock.release()
    threading.Thread(target=pull,daemon=True).start()
    return {'started':True}
