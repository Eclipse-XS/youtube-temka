"""Owned controlled 2+ hour VOD: sparse speech across four distant chapters.

The complete source is intentionally tiny, 160x90 at 1 FPS. This is a timeline,
chunking and recovery test, not a visual quality or representative speed benchmark.
"""
from factory.media import run,ffmpeg
from pathlib import Path
import json

path=Path('verification/controlled-2h.mkv')
graph='[1:a]aresample=16000,asplit=4[a][b][c][d];[b]adelay=2400000:all=1[b1];[c]adelay=4800000:all=1[c1];[d]adelay=7250000:all=1[d1];[a][b1][c1][d1]amix=inputs=4:normalize=0,apad[audio]'
run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0x204060:size=160x90:rate=1','-i','verification/source-en.mp4','-filter_complex_threads','1','-filter_complex',graph,'-map','0:v','-map','[audio]','-t','7280','-c:v','libx264','-preset','ultrafast','-crf','35','-r','1','-c:a','pcm_s16le','-threads','2',str(path)],timeout=600)
Path('verification/long-fixture.json').write_text(json.dumps({'duration':7280,'speech_chapters':[0,2400,4800,7250],'resolution':[160,90],'fps':1,'bytes':path.stat().st_size,'rights':'Locally generated test pattern and owned synthetic speech'},indent=2),encoding='utf-8')
print('Controlled fixture created:',path.stat().st_size,'bytes')
