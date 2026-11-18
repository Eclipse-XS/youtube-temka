"""Transcript-driven pause removal with one shared video/audio/caption timeline."""
from copy import deepcopy


def speech_timeline(transcript,start,end,padding=.18,min_gap=.8):
    ranges=[]
    for segment in transcript['segments']:
        units=segment.get('words') or [segment]
        for item in units:
            a=max(start,item['start']-padding);b=min(end,item['end']+padding)
            if b<=a:continue
            if ranges and a-ranges[-1][1]<min_gap:ranges[-1][1]=max(ranges[-1][1],b)
            else:ranges.append([a,b])
    if not ranges:return [[0,end-start]],transcript,start,end
    # Limit concat complexity and keep the source if there is no meaningful gap.
    if len(ranges)>80 or end-start-sum(b-a for a,b in ranges)<min_gap:
        return [[0,end-start]],transcript,start,end
    rebased=[];offset=0
    for a,b in ranges:
        for segment in transcript['segments']:
            if segment['end']<=a or segment['start']>=b:continue
            s=deepcopy(segment);s['start']=offset+max(0,segment['start']-a);s['end']=offset+min(b-a,segment['end']-a)
            if segment.get('words'):
                s['words']=[{**w,'start':offset+max(0,w['start']-a),'end':offset+min(b-a,w['end']-a)} for w in segment['words'] if w['end']>a and w['start']<b]
                s['text']=''.join(w['word'] for w in s['words'])
            rebased.append(s)
        offset+=b-a
    return [[a-start,b-start] for a,b in ranges],{**transcript,'segments':rebased},0,offset


def remove_pauses(source,output,transcript,start,end,has_audio,tick):
    from .media import run,ffmpeg
    ranges,timed,caption_start,duration=speech_timeline(transcript,start,end)
    if len(ranges)==1 and ranges[0]==[0,end-start]:return source,transcript,start,end
    filters=[];inputs=[]
    for i,(a,b) in enumerate(ranges):
        filters.append(f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]')
        if has_audio:filters.append(f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]')
        inputs.append(f'[v{i}]'+(f'[a{i}]' if has_audio else ''))
    filters.append(''.join(inputs)+f'concat=n={len(ranges)}:v=1:a={int(has_audio)}[v]'+('[a]' if has_audio else ''))
    args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-i',str(source),'-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]']
    args+=['-map','[a]','-c:a','aac'] if has_audio else ['-an']
    run(args+['-c:v','libx264','-preset','fast','-crf','18','-threads','2',str(output)],tick)
    return output,timed,caption_start,duration
