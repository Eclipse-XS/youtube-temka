"""Owned two-hour fixture assembled from small encoded blocks, without delay buffers."""
from pathlib import Path
from factory.media import run,ffmpeg,validate_output


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'scratch'/'v7-fixtures';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'owned-2h.mp4'
    common=['-c:v','libx264','-preset','ultrafast','-crf','35','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','32k','-ar','16000','-ac','1']
    voice=folder/'speech-24.mp4'
    run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-threads','2','-i',str(root/'verification'/'source-en.mp4'),'-vf','fps=1,scale=160:90','-filter_threads','1','-af','apad','-t','24',*common,str(voice)],timeout=60)
    for seconds in (10,6):
        run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0x204060:size=160x90:rate=1','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t',str(seconds),*common,str(folder/f'silence-{seconds}.mp4')],timeout=60)
    chapter=[('speech-24.mp4',24)]+[('silence-10.mp4',10)]*237+[('silence-6.mp4',6)]
    tail=[('speech-24.mp4',24)]+[('silence-10.mp4',10)]*5+[('silence-6.mp4',6)]
    manifest=folder/'two-hour.concat.txt'
    manifest.write_text(''.join(f"file '{name}'\nduration {duration}\n" for name,duration in chapter*3+tail),encoding='utf-8')
    temporary=folder/'owned-2h.rendering.mp4'
    run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','concat','-safe','1','-i',str(manifest),'-c','copy','-movflags','+faststart',str(temporary)],timeout=120)
    result=validate_output(temporary,7280,expected_audio=True)
    temporary.replace(output)
    print({'duration':result['duration'],'bytes':output.stat().st_size,'resolution':[160,90],'speech_chapters':[0,2400,4800,7200],'method':'bounded encoded blocks; stream-copy assembly'})


if __name__=='__main__':main()
