"""Representative real-frame thumbnails; no generated scenes or faces."""
from pathlib import Path
import os
import textwrap


def create(video,target,text='',tick=lambda *_:None):
    import cv2
    from .media import run,ffmpeg
    from ffmpeg_utils import escape_filter_value
    capture=cv2.VideoCapture(str(video),cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2]);fps=capture.get(cv2.CAP_PROP_FPS) or 30
    duration=(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1)/fps
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    best=None
    try:
        for ratio in (.1,.25,.4,.55,.7,.85):
            capture.set(cv2.CAP_PROP_POS_MSEC,max(0,duration*ratio)*1000)
            ok,frame=capture.read()
            if not ok:continue
            gray=cv2.cvtColor(cv2.resize(frame,(320,320)),cv2.COLOR_BGR2GRAY)
            brightness=float(gray.mean());sharpness=float(cv2.Laplacian(gray,cv2.CV_64F).var())
            faces=detector.detectMultiScale(gray,1.1,5,minSize=(25,25))
            score=min(sharpness,1500)+100*len(faces)-(500 if brightness<12 or brightness>245 else 0)
            if best is None or score>best[0]:best=(score,frame,{'selected_time':round(duration*ratio,3),'sharpness':round(sharpness,2),'brightness':round(brightness,2),'face_count':len(faces),'overlay_position':'top' if len(faces) and max(y+h for x,y,w,h in faces)>220 else 'bottom'})
    finally:capture.release()
    if best is None:raise ValueError('No real source frame was available for the thumbnail')
    _,frame,report=best
    h,w=frame.shape[:2];scale=min(1,1280/max(w,h));frame=cv2.resize(frame,(max(2,round(w*scale)),max(2,round(h*scale))))
    raw=target.with_suffix('.frame.jpg') if text else target
    if not cv2.imwrite(str(raw),frame,[cv2.IMWRITE_JPEG_QUALITY,92]):raise ValueError('Thumbnail could not be saved')
    if text:
        path=target.with_suffix('.thumbnail-text.txt');path.write_text('\n'.join(textwrap.wrap(text,width=28)),encoding='utf-8')
        font='font=Noto Sans:'
        if os.name=='nt':
            fontpath=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf'
            if fontpath.is_file():font=f"fontfile='{escape_filter_value(str(fontpath.resolve()))}':"
        y='h*0.08' if report['overlay_position']=='top' else 'h-th-h*0.08'
        graph=f"drawtext={font}textfile='{escape_filter_value(str(path.resolve()))}':expansion=none:fontcolor=white:fontsize=h/22:box=1:boxcolor=black@0.65:boxborderw=10:x=(w-tw)/2:y={y}"
        run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-i',str(raw),'-vf',graph,'-frames:v','1',str(target)],tick)
        raw.unlink(missing_ok=True);path.unlink(missing_ok=True)
    return {**report,'method':'sampled_real_frames','text_applied':text}
