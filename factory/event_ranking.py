"""Cross-modal evidence ranking. Scores are editorial heuristics."""
from bisect import bisect_right


def visual_bounds(time, cuts, minimum, maximum):
    right = bisect_right(cuts,time)
    if not 0<right<len(cuts):
        return None
    left,right = cuts[right-1],cuts[right]
    if right-left<minimum:
        return None
    length=min(right-left,maximum,max(45,minimum))
    start=max(left,min(right-length,time-length/3))
    return start,start+length


def rank(features, category):
    weights = (45,30,15,10) if category in ('gameplay','visual') else (35,20,30,15)
    return round(sum(w*features[k] for w,k in zip(weights,('event_signal','boundary','context','duration_fit'))),2)
