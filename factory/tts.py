"""Optional TTS process boundary. Ordinary clipping never imports a TTS engine."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import httpx
from . import config

VOICES={'af_heart':'en','af_bella':'en','am_michael':'en','ef_dora':'es','em_alex':'es'}
ASSETS={'kokoro-v1.0.onnx':350*1024**2,'voices-v1.0.bin':100*1024**2}
SHA256={'kokoro-v1.0.onnx':'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a','voices-v1.0.bin':'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'}
_setup_lock=threading.Lock()


def folder():
    return config.DATA/'models'/'kokoro'


def status():
    path=folder()/'setup.json'
    try: progress=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):progress=None
    return {'runtime':importlib.util.find_spec('kokoro_onnx') is not None,'ready':all((folder()/name).is_file() for name in ASSETS),'voices':VOICES,'progress':progress,'engine_license':'MIT','weights_license':'Apache-2.0','optional_worker_license':'GPL-3.0-or-later (phonemizer/eSpeak dependencies)','setup_instruction':'Enable WITH_TTS=1 during initial Docker setup and rebuild. Original audio does not require TTS.'}


def setup():
    if not _setup_lock.acquire(False):return {'started':False}
    def work():
        from jsonfile import write_json_atomic
        folder().mkdir(parents=True,exist_ok=True)
        try:
            for name,limit in ASSETS.items():
                if (folder()/name).is_file():continue
                target=folder()/(name+'.part');count=0
                with httpx.stream('GET','https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'+name,follow_redirects=True,timeout=90,trust_env=False) as response:
                    response.raise_for_status();total=int(response.headers.get('Content-Length','0')) or None
                    with target.open('wb') as out:
                        for data in response.iter_bytes(1024*1024):
                            count+=len(data)
                            if count>limit:raise ValueError('Asset exceeds expected bound')
                            out.write(data)
                            write_json_atomic(folder()/'setup.json',{'state':'DOWNLOADING','asset':name,'current':count,'total':total})
                import hashlib
                with target.open('rb') as asset:
                    if hashlib.file_digest(asset,'sha256').hexdigest()!=SHA256[name]:raise ValueError('Model checksum did not match the pinned release')
                target.replace(folder()/name)
            write_json_atomic(folder()/'setup.json',{'state':'READY'})
        except Exception:
            write_json_atomic(folder()/'setup.json',{'state':'FAILED','error':'Model download failed; check network and model-cache disk space.'})
        finally:_setup_lock.release()
    threading.Thread(target=work,daemon=True).start()
    return {'started':True}


def synthesize(text,voice,speed,language,path,tick=lambda *_:None):
    if VOICES.get(voice)!=language:raise ValueError('Choose a Kokoro voice matching the detected EN/ES language. Other languages retain original audio.')
    state=status()
    if not state['runtime'] or not state['ready']:raise ValueError('Optional Kokoro is not ready. Complete its one-time setup in Settings or select Original Audio.')
    if not text.strip():raise ValueError('Voice-over needs explicit text or an actual spoken transcript')
    from .media import run
    payload=Path(path).with_suffix('.tts.json')
    payload.write_text(json.dumps({'text':text,'voice':voice,'speed':speed,'language':language}),encoding='utf-8')
    run([sys.executable,'-m','factory.tts_worker',str(folder()),str(payload),str(path)],tick,timeout=300)
    payload.unlink(missing_ok=True)
    return path
