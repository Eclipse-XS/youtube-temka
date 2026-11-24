"""One-to-one ranked detection metrics for independently annotated gameplay."""
from collections import Counter


def covers(candidate, interval):
    return candidate['start'] <= interval[0] and candidate['end'] >= interval[1]


def eligible(candidate, event):
    start, end = event['essential']
    overlap = min(candidate['end'], end) - max(candidate['start'], start)
    return (candidate['source'] == event['source'] and overlap >= .8 * (end - start)
            and candidate['start'] <= event['trigger'] < candidate['end'])


def match(candidates, events, *, require_payoff):
    """Use augmenting paths so nearby overlapping events get distinct clips."""
    edges = [[index for index, event in enumerate(events) if eligible(candidate, event)
              and (not require_payoff or not event['payoff'] or covers(candidate, event['payoff']))]
             for candidate in candidates]
    assigned = {}

    def assign(candidate, seen):
        for event in edges[candidate]:
            if event in seen:
                continue
            seen.add(event)
            if event not in assigned or assign(assigned[event], seen):
                assigned[event] = candidate
                return True
        return False

    for index in range(len(candidates)):
        assign(index, set())
    return assigned


def evaluate(candidates, events, negatives):
    matched = match(candidates, events, require_payoff=True)
    essential = match(candidates, events, require_payoff=False)
    low_motion = {index for index, event in enumerate(events) if event['low_motion_or_silent']}
    known_payoffs = [(index, candidate) for index, candidate in essential.items() if events[index]['payoff']]
    preserved = sum(covers(candidates[candidate], events[index]['payoff']) for index, candidate in known_payoffs)
    by_category = Counter(event['category'] for event in events)
    matched_by_category = Counter(events[index]['category'] for index in matched)

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    false_candidates = [candidate for index, candidate in enumerate(candidates) if index not in matched.values()]
    return {'returned_candidates': len(candidates), 'events': len(events), 'negative_examples': len(negatives),
            'matches': len(matched), 'precision_at_k': ratio(len(matched), len(candidates)),
            'recall_at_k': ratio(len(matched), len(events)),
            'low_motion_recall': ratio(len(low_motion.intersection(matched)), len(low_motion)),
            'payoff_preservation': ratio(preserved, len(known_payoffs)),
            'payoff_preservation_denominator': len(known_payoffs),
            'false_candidates_overlapping_negatives': sum(any(
                candidate['source'] == negative['source'] and
                max(candidate['start'], negative['interval'][0]) < min(candidate['end'], negative['interval'][1])
                for negative in negatives) for candidate in false_candidates),
            'by_category': {category: {'annotated': count, 'matched': matched_by_category[category]}
                            for category, count in sorted(by_category.items())}}
