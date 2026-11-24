"""Selection and transcript assembly for source-aware long-form timelines."""
from collections import defaultdict

from .render_timeline import fingerprint


GAMEPLAY_THEMES = {
    'vehicle_crash': 'vehicles', 'stunt_fail': 'vehicles', 'police_chase_fail': 'vehicles',
    'physics_glitch': 'physics', 'animation_glitch': 'physics', 'ragdoll': 'physics',
    'unexpected_survival': 'survival', 'unexpected_death': 'survival', 'combat_fail': 'survival',
    'absurd_interaction': 'interactions', 'unexpected_collision': 'interactions',
    'visual_reaction': 'interactions', 'npc_behavior': 'interactions',
}


def gameplay_event(candidate):
    source = candidate['source_id']
    start, end = candidate['start_seconds'], candidate['end_seconds']
    offset = candidate.get('source_offset', 0)
    review = candidate.get('visual_review') or {}
    times = candidate.get('source_frame_times', [])
    supported = bool(review and not review['uncertain'] and len(times) == 3)
    category = review['category'] if supported else 'unknown_event'
    beats = []
    trigger, payoff = candidate.get('event_seconds'), None
    if supported and review.get('trigger_frame'):
        trigger = times[review['trigger_frame'] - 1] - offset
    if supported and review.get('payoff_frame'):
        payoff = times[review['payoff_frame'] - 1] - offset
    if supported and review.get('setup') and trigger is not None and start < trigger and times[0] >= start + offset:
        beats.append({'type': 'setup', 'source_seconds': times[0], 'description': review['setup'],
                      'evidence': 'frame_observation'})
    if trigger is not None and start <= trigger < end:
        beats.append({'type': 'trigger', 'source_seconds': round(offset + trigger, 3),
                      'evidence': 'frame_observation' if supported else 'visual_activity'})
    if payoff is not None and trigger is not None and start <= trigger < payoff < end:
        beats.append({'type': 'payoff', 'source_seconds': round(offset + payoff, 3),
                      'description': review['observation'], 'evidence': 'frame_observation'})
    evidence = candidate.get('evidence', {})
    following = [point for point in evidence.get('follow_through_samples', [])
                 if trigger is not None and trigger < point < end]
    return {'id': fingerprint([source, start, end, offset])[:20], 'source_id': source,
            'source_start': start + offset, 'source_end': end + offset,
            'category': category, 'theme': GAMEPLAY_THEMES.get(category), 'beats': beats,
            'complete': {beat['type'] for beat in beats} == {'setup', 'trigger', 'payoff'},
            'editorial_uncertainty': 'model_hypothesis' if supported else 'visual_signal_only',
            'follow_through_source_seconds': [round(offset + point, 3) for point in following]}


def plan_gameplay(groups, count, target, source_preferences):
    """Sequence bounded, non-overlapping event windows using observed evidence."""
    pool = []
    for group in groups:
        for candidate in group:
            event = gameplay_event(candidate)
            score = candidate.get('score', 0)
            if event['editorial_uncertainty'] == 'visual_signal_only' and score < 12:
                continue
            preferences = source_preferences[event['source_id']]
            if preferences.event_categories and event['category'] not in preferences.event_categories:
                continue
            length = candidate['end_seconds'] - candidate['start_seconds']
            preference_gap = (abs(length - preferences.preferred_event_duration) /
                              preferences.preferred_event_duration if preferences.preferred_event_duration else 0)
            quality = score + 12 * event['complete'] + 3 * preferences.priority - min(5, preference_gap * 5)
            pool.append((candidate, event, length, quality))

    selected = []
    duration = 0
    contributions = defaultdict(float)
    ranges = defaultdict(list)
    while pool and len(selected) < count and duration < target * .95:
        previous = selected[-1][1] if selected else None

        def fit(option):
            _, event, length, _ = option
            source = event['source_id']
            maximum = source_preferences[source].max_contribution
            return (duration + length <= target * 1.05 and
                    (maximum is None or contributions[source] + length <= maximum) and
                    all(event['source_end'] <= start or event['source_start'] >= end
                        for start, end in ranges[source]))

        def rank(option):
            _, event, length, quality = option
            theme_link = previous and event['theme'] and event['theme'] == previous['theme']
            new_source = previous and event['source_id'] != previous['source_id']
            return (quality + 6 * bool(theme_link) + 5 * bool(new_source) - min(6, length * .12),
                    event['complete'], -event['source_start'])

        pool = [option for option in pool if fit(option)]
        if not pool:
            break
        choice = max(pool, key=rank)
        pool.remove(choice)
        _, event, length, _ = choice
        selected.append(choice)
        duration += length
        contributions[event['source_id']] += length
        ranges[event['source_id']].append((event['source_start'], event['source_end']))

    if len(selected) > 2:
        ending = max(selected[1:], key=lambda option: (option[1]['complete'], option[3]))
        if ending[3] > selected[-1][3] + 5:
            selected.remove(ending)
            selected.append(ending)
    scenes, chapters, output = [], [], []
    for index, (candidate, event, _, _) in enumerate(selected):
        role = 'cold_open' if index == 0 else 'closing_scene' if index == len(selected) - 1 else 'scene'
        theme = event['theme']
        if not chapters or chapters[-1]['theme'] != theme:
            chapters.append({'id': len(chapters) + 1, 'theme': theme, 'scene_ids': []})
        chapters[-1]['scene_ids'].append(event['id'])
        scenes.append({'id': event['id'], 'role': role, 'event': event, 'chapter': chapters[-1]['id']})
        output.append({**candidate, 'narrative_event': event, 'narrative_role': role})
    return output, duration, {'scenes': scenes, 'chapters': chapters, 'source_contributions': dict(contributions),
                              'duration': round(duration, 3), 'target_duration': target}


def select(groups, count, target):
    ordered = [sorted(group, key=lambda c: -c.get('score',0)) for group in groups if group]
    ordered.sort(key=lambda group: -group[0].get('source_priority',1))
    selected = []
    duration = 0
    contributions = defaultdict(float)
    # Give each source with qualifying material a chance before taking seconds.
    while len(selected) < count and duration < target*.95:
        accepted = False
        for group in ordered:
            while group:
                candidate = group.pop(0)
                length = candidate['end_seconds'] - candidate['start_seconds']
                source = candidate['source_id']
                maximum = candidate.get('source_max_contribution')
                if duration + length <= target*1.05 and (maximum is None or contributions[source]+length <= maximum):
                    selected.append(candidate)
                    duration += length
                    contributions[source] += length
                    accepted = True
                    break
            if len(selected) == count or duration >= target*.95:
                break
        if not accepted:
            break
    # Keep adjacent excerpts from a source in chronological order. Begin with
    # the source that has the strongest opening among those we can include.
    by_source = defaultdict(list)
    for candidate in selected:
        by_source[candidate['source_id']].append(candidate)
    groups = sorted(by_source.values(),key=lambda group:-max(c.get('score',0) for c in group))
    return [c for group in groups for c in sorted(group,key=lambda c:c['start_seconds'])], duration


def append_transcript(output, transcript, start, end, position):
    shift = position-start
    if transcript.get('language') and output['language'] is None:
        output['language'] = transcript['language']
    for segment in transcript['segments']:
        if segment['end'] <= start or segment['start'] >= end:
            continue
        words = [{**word,'start':max(start,word['start'])+shift,
                  'end':min(end,word['end'])+shift} for word in segment.get('words',[])
                 if word['end'] > start and word['start'] < end]
        output['segments'].append({**segment,'start':max(start,segment['start'])+shift,
                                  'end':min(end,segment['end'])+shift,
                                  'text':''.join(w['word'] for w in words) if words else segment['text'],
                                  'words':words})
