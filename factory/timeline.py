"""Deterministic source/output arithmetic; editorial continuity needs review."""
import math


def connected(candidates,request,duration):
    if not candidates:return [],'No continuous event was identified'
    # Only subdivide one selected event, never concatenate unrelated highlights.
    event=max(candidates,key=lambda c:(c['end_seconds']-c['start_seconds'],c.get('score',0)))
    start=max(0,event['start_seconds']);end=min(duration,event['end_seconds'])
    span=end-start;overlap=request.series_overlap
    count=min(request.count,max(0,math.floor((span-overlap)/(request.minimum-overlap))))
    if not count:return [],'Selected event is shorter than the minimum clip duration'
    length=min(request.maximum,(span+(count-1)*overlap)/count)
    result=[]
    for i in range(count):
        a=start+i*(length-overlap);b=min(end,a+length)
        result.append({**event,'start_seconds':a,'end_seconds':b,
                       'title':event['title'],'series_title':event['title'],'part':i+1,'parts':count,
                       'editorial_review_required':True,'reason':'Continuous selected source event, chronological subdivision; review semantic continuity'})
    return result,f'{count}/{request.count} parts from one selected source event; overlap {overlap:g}s. Editorial continuity requires review.'


def manifest(candidates,request):
    position=0;segments=[]
    for i,item in enumerate(candidates):
        length=item['end_seconds']-item['start_seconds']
        segments.append({'segment_id':str(i+1),'source_start_ms':round((request.start+item['start_seconds'])*1000),
                         'source_end_ms':round((request.start+item['end_seconds'])*1000),
                         'output_start_ms':round(position*1000),'output_end_ms':round((position+length)*1000),
                         'edit_start_ms':round(position*1000),'edit_end_ms':round((position+length)*1000),
                         'transition':'cut','subtitle_track':bool(request.captions),
                         'overlay_assets':[request.logo_asset] if request.logo_asset else [],'audio_settings':{'mode':request.audio_mode}})
        position+=length
    return {'schema_version':1,'segments':segments,'duration_ms':round(position*1000)}
