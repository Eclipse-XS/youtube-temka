"""Render a review package from two authorized gameplay recordings."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first',type=Path)
    parser.add_argument('second',type=Path)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--speech',type=Path)
    parser.add_argument('--label',default='NEVERBALL')
    parser.add_argument('--rights-confirmed',action='store_true',required=True)
    args=parser.parse_args()
    workspace=args.workspace.resolve()
    workspace.mkdir(parents=True,exist_ok=False)
    os.environ.update(PYTHON_DOTENV_DISABLED='1',FFMPEG_ENCODER='x264',FACTORY_DATA=str(workspace/'data'),
                      OLLAMA_URL='http://127.0.0.1:1',FACTORY_HOST_LOCK_DIR=str(workspace/'lock'))
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

    from factory import config, media, pipeline, store
    from factory.models import JobRequest

    uploads=config.SCRATCH/'uploads'
    uploads.mkdir(parents=True)
    for path,name in ((args.first,'gameplay-one.mp4'),(args.second,'gameplay-two.mp4')):
        shutil.copyfile(path,uploads/name)
    source='upload:gameplay-one.mp4'
    options={'source':source,'rights_confirmed':args.rights_confirmed,'workflow':'highlights',
             'ranking_profile':'gameplay_only','minimum':5,'maximum':10,'count':1,'captions':False,
             'save_drive':False,'max_text_model_calls':0,'preset':'blur','end':20}
    outputs={}

    def run():
        pipeline.process(store.claim('gameplay-acceptance'))

    def deliver(label,job):
        job=store.get(job['id'])
        result=job['result']
        evidence={'state':job['state'],'error':job['error'],'candidates':result.get('candidates'),
                  'narrative_plan':result.get('narrative_plan')}
        if job['state']=='READY':
            root=config.SCRATCH/job['id']
            output=result['outputs'][0]
            target=workspace/(label+'.mp4')
            shutil.copyfile(root/output['name'],target)
            evidence['output']=target.name
            evidence['validation']=output['validation']
            evidence['render']=json.loads((root/'reproducibility.json').read_text(encoding='utf-8'))
            evidence['timeline']=json.loads((root/'timeline.json').read_text(encoding='utf-8'))
        outputs[label]=evidence

    silent=store.create(JobRequest(**options,text_mode='none',audio_mode='silent').model_dump())
    run()
    deliver('silent-no-hook',silent)
    manual=store.create(JobRequest(**options,text_mode='custom',hook=args.label,hook_pinned=True).model_dump())
    run()
    deliver('manual-full-duration-hook',manual)

    if args.speech:
        voice=uploads/'gameplay-speech.mp4'
        media.run([media.ffmpeg(),'-y','-v','error','-i',str(uploads/'gameplay-one.mp4'),'-i',str(args.speech.resolve()),
                   '-map','0:v:0','-map','1:a:0','-c:v','copy','-af','apad','-c:a','aac','-t','20',str(voice)])
        speech=store.create(JobRequest(**{**options,'source':'upload:'+voice.name},text_mode='none').model_dump())
        run()
        deliver('spoken-audio',speech)

    compilation=JobRequest(**{**options,'count':4,'workflow':'compilation'},destination='video',
                           review_before_render=True,target_duration=24,sources=[{'source':source,'end':20},
                           {'source':'upload:gameplay-two.mp4','end':20}])
    long=store.create(compilation.model_dump())
    run()
    plan=store.get(long['id'])['result'].get('edit_plan')
    if plan:
        edits=[{key:scene[key] for key in ('id','start_seconds','end_seconds','transition')}
               for scene in plan['segments']]
        approved=store.edit_plan(long['id'],plan['revision'],edits,None,approve=True)
        run()
        deliver('multi-source',long)
        if outputs['multi-source']['state']=='READY':
            edits.reverse()
            edits[0]['hook']={'text':args.label+' REPLAY','start':.5,'end':2}
            edits[0]['effects']=[{'kind':'punch_in','start':1,'end':2,'scale':1.2}]
            draft=store.edit_plan(long['id'],approved['revision'],edits,None,preview=True)
            run()
            preview=store.get(long['id'])['result'].get('preview')
            if preview:
                root=config.SCRATCH/long['id']
                shutil.copyfile(root/preview['files'][0],workspace/'revised-preview.mp4')
                store.edit_plan(long['id'],draft['revision'],edits,None,approve=True)
                run()
                deliver('revised-multi-source',long)
    else:
        deliver('multi-source',long)
    (workspace/'gameplay-results.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({label:result['state'] for label,result in outputs.items()}))


if __name__=='__main__':
    main()
