"""FFmpeg filters for validated, scene-relative timeline effects."""
import os
from math import ceil
from pathlib import Path

from ffmpeg_utils import escape_filter_value
from .render_timeline import AUDIO_EFFECTS, OVERLAY_EFFECTS, SPATIAL_EFFECTS, TEMPORAL_EFFECTS


def playback_ranges(effects, duration):
    temporal = sorted((effect for effect in effects if effect.kind in TEMPORAL_EFFECTS), key=lambda effect: effect.start)
    if not temporal:
        return []
    ranges = []
    position = 0
    for effect in temporal:
        if position < effect.start:
            ranges.append((position, effect.start, position, 1))
        source = effect.replay_start if effect.kind == 'replay' else effect.start
        rate = {'freeze_frame': 0, 'slow_motion': effect.rate}.get(effect.kind, 1)
        ranges.append((effect.start, effect.end, source, rate))
        position = effect.end
    if position + .001 < duration:
        ranges.append((position, duration, position, 1))
    return ranges


def retime_transcript(transcript, ranges, offset):
    from .compilation import append_transcript

    timed = {'language': transcript['language'], 'segments': []}
    for begin, end, source, rate in ranges:
        if not rate:
            continue
        part = {'language': transcript['language'], 'segments': []}
        source_start = offset + source
        append_transcript(part, transcript, source_start, source_start + (end - begin) * rate, 0)
        for segment in part['segments']:
            for item in [segment, *segment['words']]:
                for key in ('start', 'end'):
                    item[key] = offset + begin + item[key] / rate
            timed['segments'].append(segment)
    return timed


def playback_graph(ranges, has_audio):
    if not ranges:
        return [], '[0:v]', '[0:a]'
    count = len(ranges)
    parts = [f'[0:v]split={count}' + ''.join(f'[vs{i}]' for i in range(count))]
    if has_audio:
        parts.append(f'[0:a]asplit={count}' + ''.join(f'[as{i}]' for i in range(count)))
    for i, (begin, end, source, rate) in enumerate(ranges):
        duration = end - begin
        if rate:
            limit = source + duration * rate
            video = f'trim=start={source}:end={limit},setpts=(PTS-STARTPTS)/{rate}'
        else:
            video = f'trim=start={source},setpts=PTS-STARTPTS,fps=30,trim=end_frame=1'
        parts.append(f'[vs{i}]{video},tpad=stop_mode=clone:stop={ceil(duration * 30)},'
                     f'fps=30,trim=duration={duration}[vt{i}]')
        if has_audio:
            if rate:
                tempo = f'atempo={rate},' if rate >= .5 else f'atempo=.5,atempo={rate * 2},'
                audio = f'[as{i}]atrim=start={source}:end={limit},asetpts=PTS-STARTPTS,{tempo if rate != 1 else ""}apad'
            else:
                parts.append(f'[as{i}]anullsink')
                audio = 'anullsrc=r=48000:cl=stereo'
            parts.append(f'{audio},aformat=sample_rates=48000:channel_layouts=stereo,atrim=duration={duration}[at{i}]')
    parts.append(''.join(f'[vt{i}]' for i in range(count)) + f'concat=n={count}:v=1:a=0[retimedv]')
    if has_audio:
        parts.append(''.join(f'[at{i}]' for i in range(count)) + f'concat=n={count}:v=0:a=1[retimeda]')
    return parts, '[retimedv]', '[retimeda]'


def font_option(family='sans'):
    name = {'sans': 'Noto Sans', 'serif': 'Noto Serif', 'mono': 'DejaVu Sans Mono'}[family]
    if os.name == 'nt':
        filename = {'sans': 'arial.ttf', 'serif': 'times.ttf', 'mono': 'consola.ttf'}[family]
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename
        if font.is_file():
            return f"fontfile='{escape_filter_value(str(font.resolve()))}':"
    return f"font='{name}':"


def time_window(effect, clock='t'):
    return f'gte({clock},{effect.start})*lt({clock},{effect.end})'


def visual_graph(effects, args, video, next_input, width, height, output, asset_paths):
    from .assets import asset_path

    parts = []
    spatial = [effect for effect in effects if effect.kind in SPATIAL_EFFECTS]
    if spatial:
        zoom, x, y = '1', '.5', '.5'
        for effect in spatial:
            window = time_window(effect, 'on/30')
            scale = effect.scale
            if effect.kind == 'animated_zoom':
                scale = f'1+({scale}-1)*sin(PI*(on/30-{effect.start})/({effect.end}-{effect.start}))'
            zoom = f'if({window},{scale},{zoom})'
            x = f'if({window},{effect.x},{x})'
            y = f'if({window},{effect.y},{y})'
        parts.append(f"{video}fps=30,zoompan=z='{zoom}':x='(iw-iw/zoom)*({x})':"
                     f"y='(ih-ih/zoom)*({y})':d=1:s={width}x{height}:fps=30[spatial]")
        video = '[spatial]'
    for i, effect in enumerate(effects):
        kind = effect.kind
        window = time_window(effect)
        label = f'[visual{i}]'
        if kind == 'visual_accent':
            parts.append(f"{video}drawbox=x=0:y=0:w=iw:h=ih:t={max(4, width//100)}:"
                         f"color={effect.color}:enable='{window}'{label}")
        elif kind == 'text_overlay':
            text = output.with_suffix(f'.effect-{i}.txt')
            text.write_text(effect.text, encoding='utf-8', newline='')
            parts.append(f"{video}drawtext={font_option()}textfile='{escape_filter_value(str(text.resolve()))}':"
                         f"expansion=none:fontcolor={effect.color}:fontsize={max(22, height//20)}:"
                         f"borderw=2:x='(w-tw)*{effect.x}':y='(h-th)*{effect.y}':enable='{window}'{label}")
        elif kind in OVERLAY_EFFECTS:
            image = kind == 'image_overlay'
            library = 'logos' if image else 'backgrounds'
            path = getattr(asset_paths,'by_name',{}).get((library,effect.asset)) or asset_path(library,effect.asset)
            args.extend(['-loop' if image else '-stream_loop', '1' if image else '-1', '-threads', '1', '-i', str(path)])
            parts.append(f'[{next_input}:v]scale={width//3}:-2,setpts=PTS-STARTPTS+{effect.start}/TB[insert{i}]')
            parts.append(f"{video}[insert{i}]overlay=x='(W-w)*{effect.x}':y='(H-h)*{effect.y}':"
                         f"eof_action=pass:enable='{window}'{label}")
            next_input += 1
        else:
            continue
        video = label
    return parts, video, next_input


def audio_graph(effects, audio):
    parts = []
    for i, effect in enumerate(effect for effect in effects if effect.kind in AUDIO_EFFECTS):
        label = f'[audioeffect{i}]'
        if effect.kind == 'gain':
            filt = f"volume={effect.gain}:enable='{time_window(effect)}'"
        else:
            filt = f'afade=t={effect.fade_direction}:st={effect.start}:d={effect.end - effect.start}'
        parts.append(f'{audio}{filt}{label}')
        audio = label
    if parts:
        parts.append(f'{audio}alimiter=limit=0.707945:level=false:latency=true[audiolimited]')
        audio = '[audiolimited]'
    return parts, audio
