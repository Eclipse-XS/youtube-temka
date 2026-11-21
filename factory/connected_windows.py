"""Bounded, evidence-checked excerpts for the Connected Story planner."""
from bisect import bisect_left, bisect_right

from .shorts import PLATFORM_MAXIMUM, planned, split
from .source_intelligence import extract_frames_at_timestamps


def plan_connected(graph, evidence, transcript, request, source, vlm):
    count, overlap = request.count, request.series_overlap
    low = count * request.minimum - (count - 1) * overlap
    high = count * min(PLATFORM_MAXIMUM, request.maximum) - (count - 1) * overlap
    preferred = (low + high) / 2
    segments = transcript.get('segments', [])
    stops = sorted({s['end'] for s in segments if s['text'].rstrip().endswith(('.', '!', '?'))})
    starts = [s['start'] for s in segments]
    shot_bounds = {s.start for s in evidence.shots} | {s.end for s in evidence.shots}
    forbidden = [b.boundary_time for b in graph.edges if not b.same_event]
    hard_boundaries = [
        edge.boundary_time for edge in graph.edges
        if edge.relation.startswith('format_break') or (
            not edge.same_event and edge.vlm_verified and edge.severity == 'strong_semantic_contradiction'
        )
    ]
    options, alternatives, decisions = [], [], []

    def alternative(event, a, b, reason, score):
        evidence = [*event.evidence[:8], reason]
        alternatives.append(planned(a, b, f'Review {event.event_id}', reason, transcript,
                                    'visual_activity', evidence, score))

    context = evidence.context
    for event in graph.events:
        if event.decision == 'REJECT':
            continue
        boundaries = sorted({event.start, event.end} | {
            t for t in [*shot_bounds, *starts, *stops] if event.start < t < event.end
        })
        endings = sorted({event.end} | {
            t for t in [*shot_bounds, *stops] if event.start < t < event.end
        })
        for a in boundaries:
            left = bisect_left(endings, a + low)
            right = bisect_right(endings, a + high)
            if left >= right:
                continue
            near = min(right - 1, bisect_left(endings, a + preferred, left, right))
            for b in sorted({endings[left], endings[right - 1], endings[near]}):
                if any(a < edge < b for edge in forbidden):
                    continue
                if any(a < br.end and b > br.start for br in graph.format_breaks):
                    continue
                if any(s['start'] + .15 < p < s['end'] - .15 for p in (a, b) for s in segments):
                    continue
                action = event.climax_time is not None and a + 3 < event.climax_time < b - 2
                payoff = event.payoff_time is not None and a + (b-a)*.5 <= event.payoff_time <= b
                score = (0.35 * event.mean_continuity + 0.15 * action + 0.15 * payoff
                         + 0.1 * (1 - abs(b - a - preferred) / max(high, 1))
                         + 0.1 * (a == event.start) + 0.1 * (b == event.end))
                options.append((score, a, b, event))

    # Reconsider CV-only splits with a separately verified, contiguous storyboard.
    # A scene change supported by VLM or a format break is an absolute boundary.
    recovered = []
    scene_ends = sorted(shot_bounds)
    for a in starts:
        event = next((e for e in graph.events if e.start <= a < e.end and e.decision != 'REJECT'), None)
        if event is None:
            continue
        limits = [t for t in hard_boundaries if t > a] + [
            br.start for br in graph.format_breaks if br.end > a
        ]
        right = min(a + high, min(limits, default=a + high))
        lo = bisect_left(scene_ends, a + low)
        hi = bisect_right(scene_ends, right)
        if lo >= hi:
            continue
        near = min(hi - 1, bisect_left(scene_ends, a + preferred, lo, hi))
        for b in sorted({scene_ends[near], scene_ends[hi - 1]}):
            if not any(a < t < b for t in forbidden):
                continue
            dialogue = [s for s in segments if a <= s['start'] and s['end'] <= b]
            if len(dialogue) < 5 or any(s['start'] < b < s['end'] for s in segments):
                continue
            # Combine early stakes/dialogue with room to see their outcome.
            talking = sum(len(s['text'].split()) for s in dialogue)
            lead = b - dialogue[-1]['end']
            if talking < 24 or lead < 6:
                continue
            score = .32 + .20 * min(talking / 72, 1) + .15 * min(lead / 25, 1)
            recovered.append((score, a, b, event))

    recovered.sort(key=lambda x: (-x[0], x[1], -x[2]))
    primary = sorted(options, key=lambda x: (-x[0], x[1], x[2]))
    queue = [(False, item) for item in primary[:1]]
    queue += [(True, item) for item in recovered] + [(False, item) for item in primary[1:]]
    examined = []
    for crosses_cut, (score, a, b, event) in queue:
        if any(max(0, min(b, y) - max(a, x)) > .8 * max(b-a, y-x) for x, y in examined):
            continue
        if len(examined) == 6:
            break
        examined.append((a, b))
        reason = 'Visual verification unavailable; narrative beats could not be confirmed.'
        finding = {'start': a, 'end': b, 'event_id': event.event_id, 'crosses_cv_splits': crosses_cut}
        if vlm is not None and source is not None:
            span = b - a
            times = [a + min(.5, .05 * span), a + .33 * span,
                     a + .78 * span, b - min(3, .06 * span)]
            frames = extract_frames_at_timestamps(source, [context.start + t for t in times])
            if len(frames) == len(times):
                excerpt = ' '.join(s['text'] for s in segments if a <= s['start'] and s['end'] <= b)
                if len(excerpt) > 700:
                    excerpt = excerpt[:320] + ' … ' + excerpt[-375:]
                verdict = vlm.verify_event_continuity(
                    [(t-context.start, frame) for t, frame in frames],
                    {'connected_story': True, 'transcript': excerpt, 'crosses_cv_split': crosses_cut,
                     'storyboard_version': 2},
                )
                beats = [verdict.setup_observed, verdict.development_observed,
                         verdict.climax_observed, verdict.payoff_observed]
                finding.update(verified=verdict.verified, confidence=verdict.confidence,
                               observations=beats, defects=verdict.defects)
                missing = ('unknown', 'unclear', 'no clear', 'none', 'not visible', 'not observed', 'not shown', 'same as')
                grounded = all(beat.strip() and not any(word in beat.lower() for word in missing) for beat in beats)
                confidence_floor = .88 if crosses_cut else .75
                if (verdict.verified and verdict.coherent_single_event
                        and verdict.confidence >= confidence_floor
                        and not verdict.contains_format_break and not verdict.contains_unrelated_scene
                        and grounded and len({beat.strip().lower() for beat in beats}) == len(beats)):
                    parts, summary = split(a, b, request, transcript, stops)
                    if parts:
                        notes = [verdict.event_summary, *beats]
                        if crosses_cut:
                            notes.append('Storyboard and dialogue verified continuity across CV cuts.')
                        else:
                            notes = [*event.evidence[:4], *notes]
                        for part in parts:
                            part.update(event_id=event.event_id, evidence=notes, score=score,
                                        setup=beats[0], development=f'{beats[1]} {beats[2]}', payoff=beats[3],
                                        confidence=verdict.confidence, semantic_verification='vlm_story_review_required',
                                        reason=f'Consecutive part of one {b-a:.1f}s story. Review the cut and payoff.')
                        decisions.append(finding | {'reason': 'Accepted for editorial review'})
                        return parts, summary + f' Story excerpt {a:.1f}–{b:.1f}s.', decisions, [], len(options) + len(recovered)
                if verdict.contains_format_break:
                    reason = 'Storyboard contains a format break.'
                elif verdict.contains_unrelated_scene:
                    reason = 'Storyboard shows unrelated scenes.'
                elif verdict.verified and verdict.coherent_single_event and grounded and verdict.confidence < confidence_floor:
                    reason = f'Story continuity confidence {verdict.confidence:.2f} is below {confidence_floor:.2f}.'
                elif verdict.verified:
                    reason = 'Storyboard did not establish setup, development, climax and payoff in one event.'
                if verdict.verified:
                    reason += f' {verdict.event_summary}'
        decisions.append(finding | {'reason': reason})
        alternative(event, a, b, reason, score)

    eligible_events = {item[3].event_id for item in options}
    for event in sorted(graph.events, key=lambda e: (-e.duration, e.start)):
        if event.decision == 'REJECT' or event.duration < 8 or event.event_id in eligible_events:
            continue
        if event.duration < low:
            reason = f'Graph event lasts {event.duration:.1f}s; the series requires at least {low:g}s.'
        else:
            reason = f'No clean story boundaries in this graph event fit {low:g}–{high:g}s.'
        if event.terminated_by_break:
            reason += f' Ends before {event.terminated_by_break}.'
        alternative(event, event.start, event.end, reason, .1 + .1 * min(1, event.duration / low))

    summary = f'No coherent {low:g}–{high:g}s story excerpt was verified. See the timestamped alternatives and event boundaries.'
    return [], summary, decisions, sorted(alternatives, key=lambda a: -a['score'])[:6], len(options) + len(recovered)
