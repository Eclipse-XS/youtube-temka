"""Bounded coarse video coverage for visual-review proposals."""
import math
from . import media
from jsonfile import write_json_atomic


def audio_samples(path,start,end,step,seek=False):
    import av
    import numpy as np

    buckets={}
    with av.open(str(path)) as container:
        if not container.streams.audio:return {}
        stream=container.streams.audio[0]
        origin=float((stream.start_time or 0)*stream.time_base)
        def include(frame,index):
            data=frame.to_ndarray()
            values=data.astype('float32')
            if data.dtype.kind in ('i','u'):
                info=np.iinfo(data.dtype)
                if data.dtype.kind=='u':values-=128
                values/=max(abs(info.min),info.max) if data.dtype.kind=='i' else 128
            total,count=buckets.get(index,(0,0))
            buckets[index]=total+float((values**2).sum()),count+values.size
        if seek:
            for index in range(math.ceil((end-start)/step)):
                target=start+origin+index*step
                container.seek(int(target/stream.time_base),stream=stream)
                for frame in container.decode(stream):
                    if frame.time is None or frame.time < target:continue
                    if frame.time >= target + .4:break
                    include(frame,index)
        else:
            for frame in container.decode(stream):
                if frame.time is None:continue
                position=frame.time-origin
                if position >= end:break
                if position >= start:include(frame,int((position-start)/step))
    result={};previous=None
    for index,(energy,count) in buckets.items():
        rms=math.sqrt(energy/count)
        result[index]={'audio_rms':round(rms,5),'audio_change':round(abs(rms-previous),5) if previous is not None else 0,
                       'sampled_silence': rms < .003}
        previous=rms
    return result


def sample(source, start, end, root, tick):
    import av
    import json
    path = root / 'visual-v2.json'
    if path.is_file():
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved['start'] == start and saved['end'] == end:
            return saved['samples']
    local = media.local_source(source)
    duration = end - start
    step = max(2, duration / 450)
    count = math.ceil(duration / step)
    samples = []
    if local:
        with av.open(str(local)) as container:
            stream = container.streams.video[0]
            origin = float((stream.start_time or 0) * stream.time_base)
            previous = None
            for index in range(count):
                offset = index * step
                target = start + offset + origin
                container.seek(int(target / stream.time_base), stream=stream)
                frame = next((frame for frame in container.decode(stream)
                              if frame.time is not None and frame.time >= target - .1), None)
                if frame is None:
                    continue
                current = frame.reformat(48, 28, format='gray').to_ndarray().astype('int16')
                motion = float(abs(current - previous).mean() / 255) if previous is not None else 0
                samples.append({'time': offset, 'motion': motion, 'cut': motion > .22})
                previous = current
                tick(index + 1, count)
    else:
        # Retrieve at most 24 short, low-resolution probes irrespective of source length.
        count = min(16, math.ceil(duration / 40))
        probe = root / 'visual-probe.mp4'
        for index in range(count):
            offset = index * duration / count
            length = min(4, duration - offset)
            try:
                media.download(source, probe, start + offset, start + offset + length, 360, False,
                               lambda *_: tick(index, count))
                audio=audio_samples(probe,0,length,1)
                with av.open(str(probe)) as container:
                    previous = None
                    last = -1
                    for frame in container.decode(video=0):
                        if frame.time is None or frame.time < last + 1 or frame.time >= length:
                            continue
                        current = frame.reformat(48, 28, format='gray').to_ndarray().astype('int16')
                        motion = float(abs(current - previous).mean() / 255) if previous is not None else 0
                        samples.append({'time': offset + frame.time, 'motion': motion, 'cut': motion > .22,
                                        **audio.get(int(frame.time),{})})
                        previous, last = current, frame.time
            except (ValueError, RuntimeError, OSError, TimeoutError):
                pass
            finally:
                probe.unlink(missing_ok=True)
            tick(index + 1, count)
    if local and samples:
        audio=audio_samples(local,start,end,step,seek=True)
        for sample in samples:
            sample.update(audio.get(round(sample['time']/step),{}))
    if samples:
        write_json_atomic(path, {'start': start, 'end': end, 'samples': samples})
    return samples
