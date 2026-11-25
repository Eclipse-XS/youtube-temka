"""One ASR process per bounded chunk; exiting releases all model VRAM."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='replace')
    source, output, language=sys.argv[1:]
    os.environ.setdefault('ASR_HOST_SLOTS','1')
    os.environ.setdefault('WHISPER_MODEL','small')
    if os.environ.get('WHISPER_DEVICE') in ('auto','cuda'):
        from .inference import release_idle_vision
        release_idle_vision()
    # CUDA is opt-in; select it only when measured free memory permits small.
    if os.environ.get('WHISPER_DEVICE')=='auto':
        try:
            free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],timeout=5,text=True).splitlines()[0])
        except (OSError,ValueError,subprocess.SubprocessError):
            free=0
        os.environ['WHISPER_DEVICE']='cuda' if free>=2500 else 'cpu'
        os.environ['WHISPER_COMPUTE']='int8_float16' if free>=2500 else 'int8'
    from transcribe_backends import run_whisper_transcription
    from subtitles import WHISPER_TRANSCRIBE_PARAMS, merge_continuation_words
    params=dict(WHISPER_TRANSCRIBE_PARAMS)
    if language!='auto':
        params['language']=language
    try:
        segments,info=run_whisper_transcription(source,**params)
    except (RuntimeError,OSError):
        if os.environ.get('WHISPER_DEVICE')!='cuda':
            raise
        # Missing CUDA libraries and unsupported kernels can raise OSError or
        # omit the word 'CUDA', which the upstream fallback does not catch.
        import transcribe_backends
        transcribe_backends._whisper_model=None
        transcribe_backends._whisper_force_cpu=True
        os.environ['WHISPER_DEVICE']='cpu'
        os.environ['WHISPER_COMPUTE']='int8'
        segments,info=run_whisper_transcription(source,**params)
    out=[]
    for s in segments:
        out.append({'start':float(s.start),'end':float(s.end),'text':s.text,'confidence':float(s.avg_logprob), 'words':merge_continuation_words([{'word':w.word,'start':float(w.start),'end':float(w.end)} for w in (s.words or [])])})
    from jsonfile import write_json_atomic
    from subtitles import get_whisper_config
    import transcribe_backends
    actual=get_whisper_config()
    write_json_atomic(output,{'language':info.language,'segments':out,'text':' '.join(s['text'] for s in out),'inference':{'device':'cpu' if transcribe_backends._whisper_force_cpu else actual['device'],'compute_type':actual['compute_type'],'model':actual['model_size']}},ensure_ascii=True)


if __name__=='__main__':
    main()
