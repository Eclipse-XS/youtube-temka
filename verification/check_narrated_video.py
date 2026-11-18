"""Real explicit Kokoro narration + retranscribed word-aligned captions."""
import json
from pathlib import Path
import time
from factory import media
from factory.models import JobRequest

request=JobRequest(source='verification fixture',rights_confirmed=True,save_drive=False,preset='blur',audio_mode='voiceover',language='en',tts_voice='af_heart',tts_text='A clear, friendly voice for your next video. Every sentence should sound natural.',captions=True)
started=time.monotonic();output=Path('verification/narrated-kokoro.mp4')
media.render(Path('verification/source-en.mp4'),output,{'language':'en','segments':[]},0,10,request)
result=json.loads(output.with_suffix('.validation.json').read_text(encoding='utf-8'))
result['elapsed_seconds']=round(time.monotonic()-started,2)
result['word_aligned_captions']=bool(output.with_suffix('.voice.json').is_file())
Path('verification/narrated-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(result)
