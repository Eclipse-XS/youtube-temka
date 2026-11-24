"""Persisted edit decisions compiled into the existing FFmpeg scene renderer."""
from collections import defaultdict
from hashlib import sha256
import json

from .models import TimelineHook, TimelineSound


SCHEMA_VERSION = 3
HOOK_STYLE = ('hook_position', 'hook_x', 'hook_y', 'hook_font_size', 'hook_font',
              'hook_color', 'hook_outline', 'hook_shadow', 'hook_box', 'hook_box_opacity',
              'hook_padding', 'hook_wrap')
TRACKS = {'primary_video': {'scene'}, 'game_audio': {'original', 'silent', 'voiceover'},
          'music': {'music'}, 'sound_effects': {'sound'}, 'captions': {'captions'},
          'hooks': {'hook', 'automatic_hook'}, 'branding': {'logo', 'cta'},
          'transitions': {'cut', 'fade'}}
SOUND_DURATIONS = {'impact': 240, 'comedic_accent': 270, 'whoosh': 320, 'bass_hit': 400}


def fingerprint(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_scene_edits(scene, duration):
    if scene.get('hook') is not None:
        hook = TimelineHook.model_validate(scene['hook'])
        if hook.text and not 0 <= hook.start < (hook.end if hook.end is not None else duration) <= duration + 1e-8:
            raise ValueError('Hook interval must be inside the scene')
    for sound in scene.get('sounds', []):
        sound = TimelineSound.model_validate(sound)
        if sound.start + SOUND_DURATIONS[sound.kind] / 1000 > duration + 1e-8:
            raise ValueError('Sound effect must fit inside the scene')


def build(candidates, request, source_limits, revision, target_duration=None):
    events = []
    segments = []
    position = 0
    for index, candidate in enumerate(candidates):
        scene_id = str(candidate.get('id', index + 1))
        source = candidate.get('source_id', 'source-1')
        offset = candidate.get('source_offset', request.start)
        start = round((offset + candidate['start_seconds']) * 1000)
        end = round((offset + candidate['end_seconds']) * 1000)
        duration = end - start
        validate_scene_edits(candidate, candidate['end_seconds'] - candidate['start_seconds'])
        finishing = position + duration
        video_id = scene_id + ':video'

        def event(track, kind, *, name=None, begin=0, finish=duration, asset=source, **parameters):
            events.append({'id': scene_id + ':' + (name or kind), 'scene_id': scene_id,
                           'track_id': track, 'type': kind, 'source_asset_id': asset,
                           'source_start_ms': start, 'source_end_ms': end,
                           'start_ms': position + begin, 'end_ms': position + finish,
                           'parameters': parameters, 'revision': revision,
                           'dependencies': [] if kind == 'scene' else [video_id]})

        event('primary_video', 'scene', name='video', candidate=candidate, source_offset=offset,
              silence_removal=request.silence_removal)
        mode = request.audio_mode
        event('game_audio', mode if mode != 'music' else 'original')
        if mode == 'music' and request.music_asset:
            event('music', 'music', asset=request.music_asset, name='music')
        for sound_index, spec in enumerate(candidate.get('sounds', []), 1):
            sound = TimelineSound.model_validate(spec)
            begin = round(sound.start * 1000)
            event('sound_effects', 'sound', name=f'sound-{sound.id or sound_index}', begin=begin,
                  finish=begin + SOUND_DURATIONS[sound.kind], asset='procedural:' + sound.kind,
                  kind_name=sound.kind, gain=sound.gain)
        if request.captions:
            event('captions', 'captions', style=request.caption_style,
                  appearance=request.caption_appearance.model_dump(), language=request.subtitle_language)
        if request.logo_asset:
            event('branding', 'logo', asset=request.logo_asset)
        if request.cta_text and (request.mode != 'longs' or index == len(candidates) - 1):
            event('branding', 'cta', begin=max(0, duration - 4000), text=request.cta_text)
        manual = candidate.get('hook')
        if manual is not None:
            hook = TimelineHook.model_validate(manual)
            text, begin, finish = hook.text, round(hook.start * 1000), round(hook.end * 1000) if hook.end is not None else duration
            automatic = False
        else:
            eligible = request.mode != 'longs' or index == 0
            text = request.hook if eligible else ''
            automatic = eligible and not text and request.text_mode in ('static_hook', 'hook_subtitles')
            begin = round(request.hook_start * 1000)
            finish = duration if request.hook_pinned else min(duration, begin + round(request.hook_duration * 1000))
        if (text or automatic) and begin < finish:
            event('hooks', 'automatic_hook' if automatic else 'hook', begin=begin, finish=finish,
                  text=text, **{key: getattr(request, key) for key in HOOK_STYLE})
        transition = candidate.get('transition', request.transition)
        event('transitions', transition, duration_ms=min(250, duration // 4) if transition == 'fade' else 0)
        segments.append({'segment_id': scene_id, 'source_id': source, 'source_start_ms': start,
                         'source_end_ms': end, 'output_start_ms': position, 'output_end_ms': finishing,
                         'edit_start_ms': position, 'edit_end_ms': finishing, 'transition': transition,
                         'subtitle_track': request.captions, 'overlay_assets': [request.logo_asset] if request.logo_asset else [],
                         'audio_settings': {'mode': mode}})
        position = finishing
    timeline = {'schema_version': SCHEMA_VERSION, 'revision': revision, 'events': events,
                'source_limits': {key: round(end * 1000) for key, end in source_limits.items()},
                'segments': segments, 'duration_ms': position}
    if target_duration is not None:
        timeline['target_duration_ms'] = round(target_duration * 1000)
    return timeline


def compile_scenes(timeline, request):
    if timeline['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Unsupported render timeline version')
    events = timeline['events']
    ids = {event['id'] for event in events}
    if len(ids) != len(events):
        raise ValueError('Timeline contains duplicate event IDs')
    by_scene = defaultdict(list)
    for event in events:
        if event['type'] not in TRACKS.get(event['track_id'], ()):
            raise ValueError(f"Unsupported timeline event: {event['track_id']}/{event['type']}")
        if event['revision'] != timeline['revision'] or not set(event['dependencies']) <= ids:
            raise ValueError('Invalid timeline event revision or dependency')
        by_scene[event['scene_id']].append(event)
    primary = sorted((event for event in events if event['type'] == 'scene'), key=lambda event: event['start_ms'])
    if not primary or len(primary) != len(by_scene):
        raise ValueError('Each scene requires one primary video event')
    scenes = []
    position = 0
    for video in primary:
        source = video['source_asset_id']
        start, end = video['source_start_ms'], video['source_end_ms']
        begin, finish = video['start_ms'], video['end_ms']
        if source not in timeline['source_limits'] or not 0 <= start < end <= timeline['source_limits'][source]:
            raise ValueError(f'Scene is outside its source bounds: {source}')
        if begin != position or finish - begin != end - start:
            raise ValueError('Primary video must be contiguous and match the source duration')
        scene_events = defaultdict(list)
        for event in by_scene[video['scene_id']]:
            if not begin <= event['start_ms'] < event['end_ms'] <= finish:
                raise ValueError(f"Event is outside its scene: {event['id']}")
            if event is not video and event['dependencies'] != [video['id']]:
                raise ValueError(f"Event has invalid scene dependencies: {event['id']}")
            scene_events[event['track_id']].append(event)
        for track in ('game_audio', 'music', 'captions', 'hooks', 'transitions'):
            if len(scene_events[track]) > 1:
                raise ValueError(f'Overlapping events on the {track} track')

        options = {'hook': '', 'cta_text': '', 'captions': False, 'logo_asset': None, 'music_asset': None,
                   'audio_mode': 'silent', 'transition': 'cut', 'silence_removal': video['parameters']['silence_removal']}
        automatic_hook = None
        transition_seconds = None
        sounds = []
        for event in by_scene[video['scene_id']]:
            kind, params = event['type'], event['parameters']
            local_start = event['start_ms'] - begin
            length = event['end_ms'] - event['start_ms']
            if kind in ('hook', 'automatic_hook'):
                options.update(hook=params['text'], hook_start=local_start / 1000,
                               hook_pinned=event['end_ms'] == finish, hook_duration=length / 1000,
                               **{key: params[key] for key in HOOK_STYLE})
                if kind == 'automatic_hook':
                    automatic_hook = event['id']
            elif kind in ('original', 'silent', 'voiceover'):
                options['audio_mode'] = kind
            elif kind == 'captions':
                options.update(captions=True, caption_style=params['style'], subtitle_language=params['language'],
                               caption_appearance=request.caption_appearance.model_validate(params['appearance']))
            elif kind == 'logo':
                options['logo_asset'] = event['source_asset_id']
            elif kind == 'cta':
                options['cta_text'] = params['text']
            elif kind in ('cut', 'fade'):
                length_ok = (0 < params['duration_ms'] <= (finish - begin) / 2 if kind == 'fade'
                             else params['duration_ms'] == 0)
                if not length_ok:
                    raise ValueError('Transition duration exceeds the scene')
                options['transition'] = kind
                transition_seconds = params['duration_ms'] / 1000
            elif kind == 'sound':
                sound = TimelineSound(kind=params['kind_name'], start=local_start / 1000, gain=params['gain'])
                if length != SOUND_DURATIONS[sound.kind] or event['source_asset_id'] != 'procedural:' + sound.kind:
                    raise ValueError('Invalid procedural sound duration')
                sounds.append(sound)
        if scene_events['music']:
            options.update(audio_mode='music', music_asset=scene_events['music'][0]['source_asset_id'])
        offset = video['parameters']['source_offset']
        candidate = {**video['parameters']['candidate'], 'source_id': source, 'source_offset': offset,
                     'start_seconds': start / 1000 - offset, 'end_seconds': end / 1000 - offset}
        scenes.append((candidate, request.model_copy(update=options), automatic_hook, sounds, transition_seconds))
        position = finish
    if position != timeline['duration_ms']:
        raise ValueError('Timeline duration does not match the primary video track')
    return scenes
