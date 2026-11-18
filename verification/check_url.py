"""Real bounded licensed-source retrieval; no cookie or OAuth access."""
import json
from pathlib import Path
import time
from factory import media,config
source='https://www.youtube.com/watch?v=YE7VzlLtp-4'
started=time.monotonic()
result={'url':source,'license':'CC BY 3.0 — Blender Foundation','start':30,'end':40}
try:
    info=media.probe(source)
    result['metadata']=info
    path=config.SCRATCH/'licensed-bounded.mp4';path.parent.mkdir(parents=True,exist_ok=True)
    media.download(source,path,30,40,480)
    result.update(status='PASS',media=media.validate_output(path,10),bytes=path.stat().st_size,elapsed_seconds=round(time.monotonic()-started,2))
except Exception as error:result.update(status='FAILED',error=str(error),elapsed_seconds=round(time.monotonic()-started,2))
Path('/evidence/url-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='metadata'}))
