# SPDX-License-Identifier: GPL-3.0-or-later
# Optional standalone converter: phonemizer/eSpeak are GPL dependencies.
# See docs/licenses/GPL-3.0.txt. The HTTP app uses only the text/WAV CLI boundary.
import json
import os
from pathlib import Path
import sys


def main():
    os.environ['ONNX_PROVIDER']='CPUExecutionProvider'
    import onnxruntime as rt
    import soundfile as sf
    from kokoro_onnx import Kokoro
    assets,payload,output=map(Path,sys.argv[1:])
    request=json.loads(payload.read_text(encoding='utf-8'))
    options=rt.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session=rt.InferenceSession(str(assets/'kokoro-v1.0.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    model=Kokoro.from_session(session,str(assets/'voices-v1.0.bin'))
    samples,rate=model.create(request['text'],voice=request['voice'],speed=request['speed'],lang='en-us' if request['language']=='en' else 'es')
    if not len(samples):raise ValueError('TTS produced no audio')
    sf.write(str(output),samples,rate,subtype='PCM_16')


if __name__=='__main__':main()
