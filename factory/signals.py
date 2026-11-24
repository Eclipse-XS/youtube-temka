"""Low-resolution motion, scene and audio analysis with bounded scan windows."""
import math
from bisect import bisect_left, bisect_right
from pathlib import Path
from tempfile import TemporaryDirectory

from . import media
from .models import Candidate


WINDOW_SECONDS = 60
MAX_WINDOWS = 12
FRAME_BYTES = 64 * 36


def gameplay_proposal_limit(request):
    return request.gameplay_max_proposals or min(40, 4 * request.count)


def scan(source, request, metadata, end, resolution, root, tick):
    local = media.local_source(source)
    duration = end - request.start
    count = math.ceil(duration / WINDOW_SECONDS)
    fps = request.gameplay_scan_fps if request.gameplay_only else 2
    indices = range(count) if request.gameplay_only or count <= MAX_WINDOWS else [
        round(i * (count-1)/(MAX_WINDOWS-1)) for i in range(MAX_WINDOWS)]
    events, scenes = [], []
    black_intervals = []
    scanned = 0.0
    frames_sampled = 0
    low_resolution = max((r for r in metadata['resolutions'] if r <= 480),
                         default=min(resolution, min(metadata['resolutions'])))
    for completed,index in enumerate(indices,1):
        offset = index * WINDOW_SECONDS
        length = min(WINDOW_SECONDS, duration-offset)
        start = request.start + offset
        with TemporaryDirectory(prefix='signals-', dir=root) as folder:
            work = Path(folder)
            path = local
            seek = start
            if path is None:
                path = work/'sample.mp4'
                media.download(source, path, start, start+length, low_resolution, False, lambda *_:tick())
                seek = 0
            motion, cuts, audio, local_motion, black = scan_window(
                path, seek, length, metadata.get('has_audio'), work, lambda *_:tick(), fps, request.gameplay_only)
        scenes.extend(offset+t for t in cuts)
        for i in range(max(len(motion),len(audio))):
            visual = motion[i] if i < len(motion) else 0
            sound = audio[i] if i < len(audio) else 0
            local_change = local_motion[i] if i < len(local_motion) else 0
            if (visual or sound or local_change) and i/fps < length:
                event = (offset+i/fps, visual, sound)
                events.append((*event, local_change) if request.gameplay_only else event)
        for i, is_black in enumerate(black):
            if not is_black or i / fps >= length:
                continue
            first, last = offset + i / fps, offset + min(length, (i + 1) / fps)
            if black_intervals and math.isclose(black_intervals[-1][1], first, abs_tol=1e-6):
                black_intervals[-1][1] = last
            else:
                black_intervals.append([first, last])
        scanned += length
        frames_sampled += len(motion)
        tick(completed,len(indices))
    return events, scenes, {'scanned_seconds':round(scanned,2), 'source_seconds':round(duration,2),
                            'windows':len(indices), 'fps':fps, 'frame_size':[64,36],
                            'frames_sampled':frames_sampled,'full_range':len(indices)==count,
                            'black_intervals':black_intervals}


def scan_window(path, start, duration, has_audio, work, tick, fps=2, use_local_motion=False):
    import numpy as np

    frames = work/'frames.gray'
    samples = work/'audio.pcm'
    args = [media.ffmpeg(),'-hide_banner','-loglevel','error','-y','-threads','2',
            '-ss',str(start),'-i',str(path),'-filter_threads','1',
            '-map','0:v:0','-t',str(duration),'-vf',f'fps={fps},scale=64:36,format=gray',
            '-an','-threads','1','-f','rawvideo',str(frames)]
    if has_audio:
        args += ['-map','0:a:0?','-t',str(duration),'-vn','-ac','1','-ar','4000',
                 '-f','s16le',str(samples)]
    media.run(args, tick)
    motion, cuts, audio, local_motion, black = [], [], [], [], []
    with frames.open('rb') as stream:
        previous = None
        while data := stream.read(FRAME_BYTES):
            if len(data) != FRAME_BYTES:
                break
            frame = np.frombuffer(data,dtype=np.uint8).astype(np.int16)
            difference = np.abs(frame - previous) if previous is not None else None
            change = float(difference.mean()) / 255 if difference is not None else 0
            if use_local_motion:
                # A small moving actor can disappear in the full-frame average.
                tiles = difference.reshape(6, 6, 8, 8) if difference is not None else None
                local_motion.append(float(tiles.mean(axis=(1, 3)).max()) / 255 if tiles is not None else 0)
                black.append(np.count_nonzero(frame < 16) >= .95 * FRAME_BYTES)
            if change >= .23:
                cuts.append(len(motion)/fps)
            motion.append(change)
            previous = frame
    if samples.is_file():
        levels = []
        with samples.open('rb') as stream:
            while data := stream.read(8000//fps):
                values = np.frombuffer(data,dtype='<i2').astype(np.float32)/32768
                levels.append(float(np.sqrt(np.mean(values**2))))
        baseline = float(np.median(levels)) if levels else 0
        audio = [max(0, level-max(.025,baseline*1.5)) for level in levels]
    return motion, cuts, audio, local_motion, black


def gameplay_candidates(events, scenes, request, duration, title, coverage, source_id, limit):
    """Rank visible changes and retain their context for editorial review."""
    if duration < request.minimum:
        return []
    times=[point[0] for point in events]
    black_intervals = coverage.get('black_intervals', [])
    black_starts = [bounds[0] for bounds in black_intervals]

    def black_at(time):
        index = bisect_right(black_starts, time) - 1
        return black_intervals[index] if index >= 0 and time < black_intervals[index][1] else None

    strong, quiet = [], []
    for at,motion,audio,local_change in events:
        if black_at(at):
            continue
        left=bisect_left(times,at-2)
        right=bisect_right(times,at+2)
        neighbors=[point for point in events[left:right] if point[0]!=at]
        base=sum(point[1] for point in neighbors)/max(1,round(4*coverage['fps']))
        increase=max(0,motion-base)
        following=[point[0] for point in neighbors if point[0]>at and point[1]>=max(.025,base*1.35)]
        cut_at=bisect_left(scenes,at-.5)
        scene_cut=cut_at<len(scenes) and scenes[cut_at]<=at+.5
        local_base = sum(point[3] for point in neighbors) / max(1, round(4 * coverage['fps']))
        local_increase = max(0, local_change - local_base)
        if motion >= .025 and increase >= .015:
            kind = 'motion'
            visible = min(35, 175 * increase)
        elif (not scene_cut and 0 < motion < .025 and local_change >= .04 and
              local_change >= motion * 3 and local_increase >= .018):
            kind = 'local_motion'
            visible = min(14, 110 * local_increase)
            following = [point[0] for point in neighbors if point[0] > at and point[3] >= local_change * .65]
        else:
            continue
        follow_through=min(15,len(following)*5)
        score=visible+follow_through-(12 if scene_cut else 0)
        if score<=0:
            continue
        length=min(duration,request.maximum,max(request.minimum,8+(max(following,default=at)-at)*2))
        start=min(duration-length,max(0,at-length*.35))
        leading_black = black_at(start)
        if leading_black:
            start = leading_black[1]
        end = min(duration, start + length)
        trailing_black = black_at(max(start, end - .001))
        if trailing_black and trailing_black[0] > at:
            end = trailing_black[0]
        if end - start < request.minimum:
            continue
        record={'source_id':source_id,'start_seconds':start,'end_seconds':end,'event_seconds':at,
                'context_interval':[start,at],'payoff_seconds':None,'category':'unknown_event',
                'score':round(score,3),'heuristic_score':round(score,3),'semantic_score':None,
                'proposal_kind':kind,'confidence':.35 if score>=12 and not scene_cut else .2,
                'title':(title or 'Gameplay event')[:100],'language':'und',
                'reason':'Visual activity and temporal context suggest a moment for review.',
                'selection_method':'gameplay_signals','editorial_review_required':True,
                'editorial_uncertainty':'sampled_signals',
                'evidence':{'motion':round(motion,4),'motion_increase':round(increase,4),
                            'local_motion':round(local_change,4),'local_motion_increase':round(local_increase,4),
                            'audio_onset':round(audio,4),'possible_cut':scene_cut,'follow_through_samples':following,
                            'score_components':{'visual_change':round(visible,3),
                                                'follow_through':follow_through,'visible_payoff':None,
                                                'context_clarity':None,'visual_comprehensibility':None,
                                                'comedic_contrast':None,'event_completeness':None,
                                                'novelty':None,'hook_correspondence':None,
                                                'scene_cut_penalty':12 if scene_cut else 0}},
                'source_frame_times':[round(min(end-.02,max(start,point))+request.start,3)
                                      for point in (at-1,at,max(following,default=at+1))],
                'coverage':coverage,'analysis_model':None}
        (quiet if kind == 'local_motion' else strong).append(record)
    strong.sort(key=lambda item:(-item['score'],item['event_seconds']))
    quiet.sort(key=lambda item:(-item['score'],item['event_seconds']))
    chosen=[]

    def take(pool,limit):
        for item in pool:
            if len(chosen)>=limit:
                break
            start,end=item['start_seconds'],item['end_seconds']
            if any(min(end,c['end_seconds'])-max(start,c['start_seconds']) >= .25*min(end-start,c['end_seconds']-c['start_seconds']) for c in chosen):
                continue
            chosen.append(item)

    reserved=round(limit*request.gameplay_low_signal_fraction)
    take(quiet, reserved)
    take(strong, limit)
    take(quiet, limit)
    return sorted(chosen,key=lambda item:-item['score'])


def propose(events, scenes, request, duration, title):
    length = min(duration, (request.minimum+request.maximum)/2)
    if length < request.minimum:
        return []
    ranked = sorted(events, key=lambda e: -(e[1]*.7 + e[2]*.3))
    candidates = []
    selected = []
    for time, motion, audio in ranked:
        if motion < .065 and audio < .035:
            continue
        start = min(duration-length, max(0, time-length*.4))
        end = start + length
        near = [point for point in scenes if abs(start-point) <= 2
                and point <= time and request.minimum <= end-point <= request.maximum]
        if near:
            start = min(near,key=lambda point:abs(start-point))
        near = [point for point in scenes if abs(end-point) <= 2
                and point > time and request.minimum <= point-start <= request.maximum]
        if near:
            end = min(near,key=lambda point:abs(end-point))
        if any(min(end,b)-max(start,a) >= .25*min(end-start,b-a) for a,b in selected):
            continue
        selected.append((start,end))
        evidence = 'frame change and audio onset' if motion >= .065 and audio >= .035 else (
            'frame change' if motion >= .065 else 'audio onset')
        candidates.append(Candidate(start_seconds=start,end_seconds=end,
            score=min(78,46+100*(motion*.7+audio*.3)),title=(title or 'Source event')[:100],
            language='und',reason=f'Sampled {evidence} at {time:.1f}s; verify the event in preview',
            confidence=.35))
        if len(candidates) >= request.count:
            break
    return candidates
