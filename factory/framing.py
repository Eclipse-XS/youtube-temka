"""CPU face trajectory and FFmpeg camera path; no generative video dependency."""
from pathlib import Path


def dedupe_sendcmd_lines(xs,fps,target='crop@c'):
    # Reused from MIT OpenShorts reframe_v2.py; LICENSE/NOTICE retained.
    lines=[]
    previous=None
    for index,x in enumerate(xs):
        if x!=previous:
            lines.append(f'{index/fps:.4f} {target} x {x};')
            previous=x
    return lines


def trajectory(source,duration):
    try:
        import cv2
    except ImportError:
        return None,{'strategy':'blur_fallback','reason':'Face detector unavailable'}
    capture=cv2.VideoCapture(str(source))
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not width or not height:
        capture.release()
        return None,{'strategy':'blur_fallback','reason':'No decodable video'}
    crop_w=min(width,int(height*9/16))//2*2
    crop_h=min(height,int(crop_w*16/9))//2*2
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    camera=(width-crop_w)/2;positions=[];detections=0
    try:
        for index in range(max(1,int(duration*2)+1)):
            capture.set(cv2.CAP_PROP_POS_MSEC,index*500)
            ok,frame=capture.read()
            if not ok:break
            ratio=min(1,640/width)
            small=cv2.resize(frame,None,fx=ratio,fy=ratio)
            faces=detector.detectMultiScale(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY),1.1,5,minSize=(24,24))
            if len(faces):
                x,y,w,h=max(faces,key=lambda f:float(f[2])*f[3])
                target=max(0,min(width-crop_w,(x+w/2)/ratio-crop_w/2));detections+=1
                movement=max(-crop_w*.125,min(crop_w*.125,(target-camera)*.35))
                camera+=movement
            positions.append(int(round(camera/2))*2)
    finally:
        capture.release()
    if not detections:
        return None,{'strategy':'blur_fallback','reason':'No reliable face detected','samples':len(positions)}
    return (crop_w,crop_h,positions),{'strategy':'face_tracking','samples':len(positions),'detections':detections}
