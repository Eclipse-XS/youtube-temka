"""Owned two-hour sparse-speech fixture; tiny resolution is not a quality benchmark."""
from pathlib import Path
from factory.media import run,ffmpeg,validate_output


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'scratch'/'v7-fixtures';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'owned-2h.mp4'
    graph='[1:a]aresample=16000,asplit=4[a][b][c][d];[b]adelay=2400000:all=1[b1];[c]adelay=4800000:all=1[c1];[d]adelay=7250000:all=1[d1];[a][b1][c1][d1]amix=inputs=4:normalize=0,apad[audio]'
    run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0x204060:size=160x90:rate=1',
         '-threads','2','-i',str(root/'verification'/'source-en.mp4'),'-filter_complex_threads','1','-filter_complex',graph,
         '-map','0:v','-map','[audio]','-t','7280','-c:v','libx264','-preset','ultrafast','-crf','35','-threads','2',
         '-c:a','aac','-b:a','32k','-ac','1',str(output)],timeout=600)
    result=validate_output(output,7280,expected_audio=True)
    print({'duration':result['duration'],'bytes':output.stat().st_size,'resolution':[160,90],'speech_chapters':[0,2400,4800,7250]})


if __name__=='__main__':main()
