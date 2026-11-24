"""Measure repeated live text selection for an unchanged local transcript."""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--transcript',type=Path,required=True)
    parser.add_argument('--ollama',default='http://127.0.0.1:11445')
    args=parser.parse_args()
    root=args.workspace.resolve()
    root.mkdir(parents=True,exist_ok=False)
    os.environ.update(PYTHON_DOTENV_DISABLED='1',FACTORY_DATA=str(root/'data'),
                      FACTORY_HOST_LOCK_DIR=str(root/'lock'),OLLAMA_URL=args.ollama,OLLAMA_GPU_LAYERS='0')
    sys.path.insert(0,str(args.repo.resolve()))

    from factory import config, pipeline
    from factory.models import JobRequest
    from factory.progress import MODEL_PROGRESS, Progress

    config.initialize()
    transcript=json.loads(args.transcript.read_text(encoding='utf-8-sig'))
    duration=max(segment['end'] for segment in transcript['segments'])
    request=JobRequest(source='upload:transcript-benchmark.mp4',rights_confirmed=True,workflow='highlights',
                       count=1,minimum=5,maximum=30,save_drive=False,llm_model='qwen2.5:3b',
                       max_text_model_calls=4,max_model_seconds=180)
    results=[]
    for _ in range(2):
        operations=[]

        def update(_state=None,**kwargs):
            stage=kwargs.get('stage_update') or {}
            if stage.get('status') in ('completed','failed') and stage.get('details',{}).get('model_type')=='text':
                operations.append({'status':stage['status'],**stage['details']})

        progress=Progress(update)
        progress.source_id='source-1'
        progress.limit_models(request,{})
        progress.begin('highlights','ANALYZING')
        token=MODEL_PROGRESS.set(progress)
        started=time.perf_counter()
        try:
            selected=pipeline.rank_media(transcript,request,{'title':'Controlled spoken fixture',
                                         'local_identity':['controlled',1]},request.source,duration,720,root,progress,([],[],{}))
        finally:
            MODEL_PROGRESS.reset(token)
        results.append({'seconds':round(time.perf_counter()-started,3),'analysis':selected['analysis'],
                        'candidates':selected['candidates'],'text_calls':len(operations),'metrics':operations,
                        'cache_hits':getattr(progress,'cache_hits',{})})
    (root/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps([{key:run[key] for key in ('seconds','analysis','text_calls','cache_hits')} for run in results]))


if __name__=='__main__':
    main()
