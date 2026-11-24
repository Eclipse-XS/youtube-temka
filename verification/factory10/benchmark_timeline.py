"""Repeat an identical local Factory workload with cold and shared caches."""
import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    work = args.workspace.resolve()
    work.mkdir(parents=True, exist_ok=False)
    os.environ.update(PYTHON_DOTENV_DISABLED='1', FFMPEG_ENCODER='x264', FACTORY_DATA=str(work/'data'),
                      OLLAMA_URL='http://127.0.0.1:1', FACTORY_HOST_LOCK_DIR=str(work/'lock'))
    sys.path.insert(0, str(args.repo.resolve()))

    from factory import config, media, pipeline, store
    from factory.models import JobRequest

    source = work/'fixture.mp4'
    if args.source:
        original = args.source.resolve(strict=True)
        media.run([media.ffmpeg(),'-y','-v','error','-threads','2','-i',str(original),
                   '-t','15','-map','0:v:0','-map','0:a:0?','-c:v','libx264','-threads','2','-c:a','aac',str(source)])
    else:
        media.run([media.ffmpeg(),'-y','-v','error','-f','lavfi','-i','testsrc2=s=640x360:r=30',
                   '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','15',
                   '-c:v','libx264','-threads','2','-c:a','aac',str(source)])
    request = JobRequest(source='upload:fixture.mp4',rights_confirmed=True,workflow='highlights',mode='longs',
                         intervals=[(0,6),(6,12)],minimum=5,maximum=8,count=2,captions=False,save_drive=False,
                         max_text_model_calls=0,end=12)

    def execute(root):
        config.DATA=root
        config.SCRATCH=root/'scratch'
        config.DB=root/'jobs.sqlite3'
        uploads=config.SCRATCH/'uploads'
        uploads.mkdir(parents=True,exist_ok=True)
        fixture=uploads/source.name
        if not fixture.is_file():
            shutil.copyfile(source,fixture)
        job=store.create(request.model_dump())
        started=time.perf_counter()
        pipeline.process(store.claim('benchmark'))
        elapsed=round(time.perf_counter()-started,3)
        result=store.get(job['id'])
        if result['state']!='READY':
            raise RuntimeError(result['error'])
        output=result['result']['outputs'][0]
        details={'seconds':elapsed,'job':job['id'],'media':str(config.SCRATCH/job['id']/output['name']),
                 'duration':output['duration'],'validation':output['validation'],
                 'cache_hits':result['result'].get('cache_hits',{})}
        return details

    cold=[execute(work/f'cold-{index+1}') for index in range(args.runs)]
    shared=work/'shared'
    priming=execute(shared)
    warm=[execute(shared) for _ in range(args.runs)]
    summary={'input':'external clip, first 15 seconds' if args.source else 'generated video and tone',
             'cold':cold,'cache_priming':priming,'warm':warm,
             'cold_median_seconds':statistics.median(item['seconds'] for item in cold),
             'warm_median_seconds':statistics.median(item['seconds'] for item in warm)}
    (work/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({key:summary[key] for key in ('input','cold_median_seconds','warm_median_seconds')}))


if __name__=='__main__':
    main()
