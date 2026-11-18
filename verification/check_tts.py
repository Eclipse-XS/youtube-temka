"""Real CPU synthesis; model assets are downloaded by Settings/setup first."""
import json
from pathlib import Path
import time
import av
import numpy as np
from factory.tts import synthesize

samples=[('en','af_heart','A clear, friendly voice for your next video. Every sentence should sound natural, with a calm pace and a warm tone.'),('es','ef_dora','Una voz clara y agradable para tu próximo vídeo. Cada frase debe sonar natural, con un ritmo tranquilo y un tono amable.')]
out=[]
for lang,voice,text in samples:
    started=time.monotonic();path=Path('verification')/('kokoro-'+lang+'.wav')
    synthesize(text,voice,1,lang,path)
    with av.open(str(path)) as container:
        duration=container.duration/av.time_base
        data=np.concatenate([frame.to_ndarray().flatten() for frame in container.decode(audio=0)])
    assert duration>3 and np.max(np.abs(data))>0
    out.append(dict(language=lang,voice=voice,seconds=round(time.monotonic()-started,2),audio_duration=duration,bytes=path.stat().st_size,non_silent=True))
Path('verification/tts-results.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out))
