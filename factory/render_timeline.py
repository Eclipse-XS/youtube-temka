"""Persisted edit decisions compiled into the existing FFmpeg scene renderer."""
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json

from .models import JobRequest, TimelineCaptionTrack, TimelineCard, TimelineEffect, TimelineHook, TimelineSound
from .audio_edit import PROCEDURAL_SOUNDS


SCHEMA_VERSION = 3
HOOK_STYLE = ('hook_position', 'hook_x', 'hook_y', 'hook_font_size', 'hook_font',
              'hook_color', 'hook_outline', 'hook_shadow', 'hook_box', 'hook_box_opacity',
              'hook_padding', 'hook_wrap')
SPATIAL_EFFECTS = {'punch_in', 'animated_zoom', 'crop'}
TEMPORAL_EFFECTS = {'freeze_frame', 'slow_motion', 'replay'}
AUDIO_EFFECTS = {'gain', 'audio_fade'}
OVERLAY_EFFECTS = {'image_overlay', 'video_overlay'}
VISUAL_EFFECTS = SPATIAL_EFFECTS | TEMPORAL_EFFECTS | {'visual_accent', 'text_overlay'}
TRACKS = {'primary_video': {'scene'}, 'game_audio': {'original', 'silent', 'voiceover'},
          'music': {'music'}, 'sound_effects': {'sound'}, 'captions': {'captions'},
          'hooks': {'hook', 'automatic_hook'}, 'branding': {'logo', 'cta', 'chapter_title'},
          'effects': VISUAL_EFFECTS | AUDIO_EFFECTS, 'secondary_video': {'video_overlay'},
          'image_overlays': {'image_overlay'},
          'intro': {'card'}, 'outro': {'card'},
          'transitions': {'cut', 'fade', 'crossfade'}}
SOUND_DURATIONS = {kind: sound[0] for kind, sound in PROCEDURAL_SOUNDS.items()}
CHAPTER_TITLES = {'vehicles': ('Vehicles', 'Транспорт'), 'physics': ('Physics', 'Фізика'),
                  'survival': ('Survival', 'Виживання'), 'interactions': ('Interactions', 'Взаємодії')}


@dataclass
class SceneRender:
    candidate: dict
    request: JobRequest
    automatic_hook: str | None
    sounds: list[TimelineSound]
    effects: list[TimelineEffect]
    caption_cues: list[dict] | None
    fade_seconds: float | None
    start_ms: int
    end_ms: int
    overlap_ms: int


@dataclass
class CardRender:
    settings: TimelineCard
    start_ms: int
    end_ms: int
    overlap_ms: int = 0


def cards_for(timeline):
    cards = {}
    for event in timeline['events']:
        if event['type'] != 'card':
            continue
        kind = event['track_id']
        settings = TimelineCard.model_validate(event['parameters'])
        length = round(settings.duration * 1000)
        if (kind not in ('intro', 'outro') or kind in cards or
                (kind == 'outro' and settings.after_cold_open) or
                event['source_asset_id'] != 'procedural:' + kind or event['dependencies'] or
                event['end_ms'] - event['start_ms'] != length):
            raise ValueError('Invalid timeline card')
        cards[kind] = CardRender(settings, event['start_ms'], event['end_ms'])
    return cards


def fingerprint(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_scene_edits(scene, duration):
    track = scene.get('caption_track')
    if track is not None:
        track = TimelineCaptionTrack.model_validate(track)
        if track.cues and track.mode != 'manual':
            raise ValueError('Only the manual caption track accepts cue edits')
        previous = 0
        for cue in track.cues:
            if not previous <= cue.start < cue.end <= duration + 1e-8:
                raise ValueError('Caption cues must be ordered, non-overlapping and inside the scene')
            previous = cue.end
    if scene.get('hook') is not None:
        hook = TimelineHook.model_validate(scene['hook'])
        if hook.text and not hook.disabled and not 0 <= hook.start < (hook.end if hook.end is not None else duration) <= duration + 1e-8:
            raise ValueError('Hook interval must be inside the scene')
    for sound in scene.get('sounds', []):
        sound = TimelineSound.model_validate(sound)
        if sound.start + SOUND_DURATIONS[sound.kind] / 1000 > duration + 1e-8:
            raise ValueError('Sound effect must fit inside the scene')
    effects = sorted((TimelineEffect.model_validate(effect) for effect in scene.get('effects', [])),
                     key=lambda effect: effect.start)
    previous_end = {'spatial': 0, 'temporal': 0}
    for effect in effects:
        if not 0 <= effect.start < effect.end <= duration + 1e-8 or effect.end - effect.start < .099:
            raise ValueError('Effect interval must be at least 100 ms and inside the scene')
        kind = effect.kind
        if kind == 'replay' and (effect.replay_start is None or effect.replay_start + effect.end - effect.start > effect.start + 1e-8):
            raise ValueError('Replay must reference footage earlier in the same scene')
        if kind == 'text_overlay' and not effect.text.strip():
            raise ValueError('Text overlay requires text')
        if kind in OVERLAY_EFFECTS and (not effect.asset or not effect.asset.endswith('.png' if kind == 'image_overlay' else '.mp4')):
            raise ValueError('Overlay requires a matching library asset')
        group = 'spatial' if kind in SPATIAL_EFFECTS else 'temporal' if kind in TEMPORAL_EFFECTS else None
        if group:
            if effect.start < previous_end[group]:
                raise ValueError(f'Overlapping {group} effects are unsupported')
            previous_end[group] = effect.end


def edit_gameplay(candidate, request):
    review = candidate.get('visual_review') or {}
    focus = review.get('action_focus')
    frames = candidate.get('source_frame_times', [])
    payoff = review.get('payoff_frame')
    if (not request.gameplay_only or request.silence_removal or request.editing_intensity == 'manual' or not focus or
            review.get('uncertain',True) or len(frames) != 3 or payoff not in (2,3)):
        return candidate
    start, end = candidate['start_seconds'], candidate['end_seconds']
    point = frames[payoff-1] - candidate.get('source_offset',request.start) - start
    duration = end-start
    if not .4 <= point <= duration-.5:
        return candidate
    begin, finish = round(point-.25,3), round(point+.45,3)
    kind = 'animated_zoom' if request.editing_intensity == 'expressive' else 'punch_in'
    distribution = dict(candidate)
    distribution.setdefault('effects',[{'kind':kind,'start':begin,'end':finish,'scale':1.22,
                                        'x':focus['x'],'y':focus['y']}])
    if (request.editing_intensity == 'expressive' and request.audio_mode != 'silent' and
            review.get('category') in ('unexpected_collision','vehicle_crash') and
            candidate.get('evidence',{}).get('audio_onset',1)<.02):
        distribution.setdefault('sounds',[{'kind':'impact','start':round(point,3),'gain':.15}])
    return distribution


def build(candidates, request, source_limits, revision, target_duration=None):
    events = []
    segments = []
    position = 0

    def add_card(kind, settings):
        length = round(settings.duration * 1000)
        events.append({'id': kind, 'scene_id': kind, 'track_id': kind, 'type': 'card',
                       'source_asset_id': 'procedural:' + kind, 'source_start_ms': 0,
                       'source_end_ms': length, 'start_ms': position, 'end_ms': position + length,
                       'parameters': settings.model_dump(), 'revision': revision, 'dependencies': []})
        return length

    if request.intro and not request.intro.after_cold_open:
        position += add_card('intro', request.intro)
    previous_theme = None
    for index, candidate in enumerate(candidates):
        candidate = edit_gameplay(candidate,request)
        scene_id = str(candidate.get('id', index + 1))
        source = candidate.get('source_id', 'source-1')
        offset = candidate.get('source_offset', request.start)
        start = round((offset + candidate['start_seconds']) * 1000)
        end = round((offset + candidate['end_seconds']) * 1000)
        duration = end - start
        validate_scene_edits(candidate, candidate['end_seconds'] - candidate['start_seconds'])
        if request.silence_removal and any(candidate.get(key) for key in ('hook', 'sounds', 'effects', 'caption_track')):
            raise ValueError('Manual timed events require pause removal to be disabled')
        transition = candidate.get('transition', request.transition)
        seconds = candidate.get('transition_duration')
        overlap = round((seconds or .5) * 1000) if transition == 'crossfade' else 0
        position -= overlap
        finishing = position + duration
        video_id = scene_id + ':video'

        def event(track, kind, *, name=None, begin=0, finish=duration, asset=source, dependencies=None, **parameters):
            events.append({'id': scene_id + ':' + (name or kind), 'scene_id': scene_id,
                           'track_id': track, 'type': kind, 'source_asset_id': asset,
                           'source_start_ms': start, 'source_end_ms': end,
                           'start_ms': position + begin, 'end_ms': position + finish,
                           'parameters': parameters, 'revision': revision,
                           'dependencies': dependencies if dependencies is not None else ([] if kind == 'scene' else [video_id])})

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
                  kind_name=sound.kind, gain=sound.gain, license='original procedural')
        for effect_index, spec in enumerate(candidate.get('effects', []), 1):
            effect = TimelineEffect.model_validate(spec)
            track = {'video_overlay': 'secondary_video', 'image_overlay': 'image_overlays'}.get(effect.kind, 'effects')
            event(track, effect.kind, name=f'effect-{effect.id or effect_index}', begin=round(effect.start * 1000),
                  finish=round(effect.end * 1000), asset=effect.asset if effect.kind in OVERLAY_EFFECTS else source,
                  **effect.model_dump(exclude={'kind', 'start', 'end', 'asset'}))
        caption_spec = candidate.get('caption_track')
        caption_track = TimelineCaptionTrack.model_validate(caption_spec) if caption_spec is not None else None
        caption_style = (caption_track.style if caption_track else None) or request.caption_style
        if caption_track and caption_track.mode != 'off' and caption_track.style is None and caption_style == 'captions_off':
            caption_style = 'clean'
        captions_on = (caption_track.mode != 'off' if caption_track else request.captions) and caption_style != 'captions_off'
        if captions_on:
            caption_style_options = request.caption_appearance.model_dump()
            if caption_track:
                caption_style_options.update(caption_track.appearance.model_dump(exclude_none=True))
            manual = caption_track is not None and caption_track.mode == 'manual'
            event('captions', 'captions', style=caption_style, appearance=caption_style_options,
                  language=None if manual else request.subtitle_language,
                  track_revision=candidate.get('caption_revision', 1),
                  cues=[cue.model_dump() for cue in caption_track.cues] if manual else None)
        if request.logo_asset:
            event('branding', 'logo', asset=request.logo_asset)
        theme = (candidate.get('narrative_event') or {}).get('theme')
        if request.chapter_titles and theme in CHAPTER_TITLES and theme != previous_theme:
            language = request.metadata_language or request.language
            text = CHAPTER_TITLES[theme][int(language == 'uk')]
            event('branding', 'chapter_title', finish=min(2500, duration), text=text)
        previous_theme = theme
        if request.cta_text and (request.mode != 'longs' or index == len(candidates) - 1):
            event('branding', 'cta', begin=max(0, duration - 4000), text=request.cta_text)
        manual = candidate.get('hook')
        if manual is not None:
            hook = TimelineHook.model_validate(manual)
            text, begin, finish = ('' if hook.disabled else hook.text), round(hook.start * 1000), round(hook.end * 1000) if hook.end is not None else duration
            automatic = False
        else:
            eligible = request.mode != 'longs' or index == 0
            text = request.hook if eligible else ''
            automatic = eligible and not text and request.text_mode in ('static_hook', 'hook_subtitles')
            begin = round(request.hook_start * 1000)
            finish = duration if request.hook_pinned else min(duration, begin + round(request.hook_duration * 1000))
        if (text or automatic) and begin < finish:
            style = {key: getattr(request,key) for key in HOOK_STYLE}
            focus = (candidate.get('visual_review') or {}).get('action_focus')
            if automatic and focus:
                y = focus['y']
                if (style['hook_position'] == 'top' and y < .35) or style['hook_position'] == 'center':
                    style['hook_position'] = 'bottom' if y < .5 else 'top'
                elif style['hook_position'] == 'bottom' and y > .65:
                    style['hook_position'] = 'top'
            event('hooks', 'automatic_hook' if automatic else 'hook', begin=begin, finish=finish,
                  text=text, **style)
        if overlap:
            adjacent = [video_id, segments[-1]['segment_id'] + ':video'] if segments else [video_id]
            event('transitions', 'crossfade', finish=overlap, duration_ms=overlap, dependencies=adjacent)
        else:
            fade = round(seconds * 1000) if seconds else min(250, duration // 4)
            event('transitions', transition, duration_ms=fade if transition == 'fade' else 0)
        segments.append({'segment_id': scene_id, 'source_id': source, 'source_start_ms': start,
                         'source_end_ms': end, 'output_start_ms': position, 'output_end_ms': finishing,
                         'edit_start_ms': position, 'edit_end_ms': finishing, 'transition': transition,
                         'subtitle_track': captions_on, 'overlay_assets': [request.logo_asset] if request.logo_asset else [],
                         'audio_settings': {'mode': mode}})
        position = finishing
        if index == 0 and request.intro and request.intro.after_cold_open:
            position += add_card('intro', request.intro)
    if request.outro:
        position += add_card('outro', request.outro)
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
    cards = cards_for(timeline)
    if cards and (request.mode != 'longs' or request.silence_removal):
        raise ValueError('Intro and outro cards require Longs with pause removal disabled')
    ids = {event['id'] for event in events}
    if len(ids) != len(events):
        raise ValueError('Timeline contains duplicate event IDs')
    by_scene = defaultdict(list)
    for event in events:
        if event['type'] not in TRACKS.get(event['track_id'], ()):
            raise ValueError(f"Unsupported timeline event: {event['track_id']}/{event['type']}")
        if event['revision'] != timeline['revision'] or not set(event['dependencies']) <= ids:
            raise ValueError('Invalid timeline event revision or dependency')
        if event['type'] != 'card':
            by_scene[event['scene_id']].append(event)
    primary = sorted((event for event in events if event['type'] == 'scene'), key=lambda event: event['start_ms'])
    if not primary or len(primary) != len(by_scene):
        raise ValueError('Each scene requires one primary video event')
    scenes = []
    position = 0
    intro = cards.get('intro')
    if intro and not intro.settings.after_cold_open:
        if intro.start_ms != 0:
            raise ValueError('Intro must start at the beginning of the timeline')
        position = intro.end_ms
    for video in primary:
        source = video['source_asset_id']
        start, end = video['source_start_ms'], video['source_end_ms']
        begin, finish = video['start_ms'], video['end_ms']
        if source not in timeline['source_limits'] or not 0 <= start < end <= timeline['source_limits'][source]:
            raise ValueError(f'Scene is outside its source bounds: {source}')
        if finish - begin != end - start:
            raise ValueError('Primary video must match the source duration')
        scene_events = defaultdict(list)
        for event in by_scene[video['scene_id']]:
            if not begin <= event['start_ms'] < event['end_ms'] <= finish:
                raise ValueError(f"Event is outside its scene: {event['id']}")
            expected = [video['id']]
            if event['type'] == 'crossfade' and scenes:
                expected.append(primary[len(scenes) - 1]['id'])
            if event is not video and event['dependencies'] != expected:
                raise ValueError(f"Event has invalid scene dependencies: {event['id']}")
            scene_events[event['track_id']].append(event)
        for track in ('game_audio', 'music', 'captions', 'hooks', 'transitions'):
            if len(scene_events[track]) > 1:
                raise ValueError(f'Overlapping events on the {track} track')

        options = {'hook': '', 'cta_text': '', 'captions': False, 'logo_asset': None, 'music_asset': None,
                   'audio_mode': 'silent', 'transition': 'cut', 'silence_removal': video['parameters']['silence_removal']}
        automatic_hook = None
        transition_seconds = None
        overlap = 0
        sounds = []
        effects = []
        caption_cues = None
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
                caption_cues = params.get('cues')
            elif kind == 'logo':
                options['logo_asset'] = event['source_asset_id']
            elif kind == 'cta':
                options['cta_text'] = params['text']
            elif kind == 'chapter_title':
                effects.append(TimelineEffect(kind='text_overlay', start=local_start / 1000,
                                              end=(local_start + length) / 1000, text=params['text'], x=.07, y=.85))
            elif kind in ('cut', 'fade', 'crossfade'):
                length_ok = (0 < params['duration_ms'] <= (finish - begin) / 2 if kind != 'cut'
                             else params['duration_ms'] == 0)
                if not length_ok:
                    raise ValueError('Transition duration exceeds the scene')
                if kind == 'crossfade':
                    overlap = params['duration_ms']
                    if (not scenes or request.mode != 'longs' or request.silence_removal or
                            local_start != 0 or overlap != length or
                            position != scenes[-1].end_ms or
                            overlap + scenes[-1].overlap_ms >= scenes[-1].end_ms - scenes[-1].start_ms):
                        raise ValueError('Crossfade requires adjacent Longs scenes, with pause removal disabled')
                else:
                    options['transition'] = kind
                    transition_seconds = params['duration_ms'] / 1000
            elif kind == 'sound':
                sound = TimelineSound(kind=params['kind_name'], start=local_start / 1000, gain=params['gain'])
                if length != SOUND_DURATIONS[sound.kind] or event['source_asset_id'] != 'procedural:' + sound.kind:
                    raise ValueError('Invalid procedural sound duration')
                sounds.append(sound)
            elif kind in VISUAL_EFFECTS | AUDIO_EFFECTS | OVERLAY_EFFECTS:
                effect = TimelineEffect(kind=kind, start=local_start / 1000, end=(local_start + length) / 1000,
                                        asset=event['source_asset_id'] if kind in OVERLAY_EFFECTS else None, **params)
                effects.append(effect)
        if scene_events['music']:
            options.update(audio_mode='music', music_asset=scene_events['music'][0]['source_asset_id'])
        if begin != position - overlap or begin < 0:
            raise ValueError('Primary video must be contiguous except at a crossfade')
        offset = video['parameters']['source_offset']
        candidate = {**video['parameters']['candidate'], 'source_id': source, 'source_offset': offset,
                     'start_seconds': start / 1000 - offset, 'end_seconds': end / 1000 - offset}
        validate_scene_edits({'effects': effects, 'caption_track':{'mode':'manual','cues':caption_cues}
                              if caption_cues is not None else None}, (finish - begin) / 1000)
        scenes.append(SceneRender(candidate, request.model_copy(update=options), automatic_hook,
                                  sounds, effects, caption_cues, transition_seconds, begin, finish, overlap))
        position = finish
        if len(scenes) == 1 and intro and intro.settings.after_cold_open:
            if intro.start_ms != position:
                raise ValueError('Cold-open intro must follow the first scene')
            position = intro.end_ms
    if 'outro' in cards:
        if cards['outro'].start_ms != position:
            raise ValueError('Outro must follow the last scene')
        position = cards['outro'].end_ms
    if position != timeline['duration_ms']:
        raise ValueError('Timeline duration does not match the primary video track')
    return scenes
